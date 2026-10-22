"""Process-level file-lock coverage; all RPCs and content are isolated fixtures."""
import copy
import concurrent.futures
import fcntl
import json
import multiprocessing
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'device'))
import bridge

TID = 'd23161f9-e454-5928-8233-3dabb2ed69e9'


class App:
    def __init__(self, ready=None, finish=None, count=None, events=None):
        self.ready, self.finish, self.count = ready, finish, count
        self.events = list(events or [])
        self.possibly_running = False
        self.writes = []

    def call(self, method, args):
        if method == 'thread/turns/list':
            return {'data': []}
        if method == 'turn/start':
            if self.count is not None:
                with self.count.get_lock():
                    self.count.value += 1
            return {'turn': {'id': 'fixture-turn', 'status': 'inProgress'}}
        return {}

    def event(self, timeout):
        if self.events:
            return self.events.pop(0)
        if self.ready:
            self.ready.set()
            if not self.finish.wait(10):
                raise AssertionError('fixture owner not released')
        return {'method': 'turn/completed', 'params': {'threadId': TID,
                'turn': {'id': 'fixture-turn', 'status': 'completed'}}}

    def write(self, obj):
        self.writes.append(obj)

    def close(self):
        pass


def owner_process(job, path, ready, finish, count):
    app = App(ready, finish, count)
    with patch.object(bridge, 'checked_app', return_value=app), \
         patch.object(bridge, 'JOURNAL', Path(path).parent):
        bridge.run_job(job, Path(path))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'request.json'
        self.job = {'id': 'f' * 64, 'requestId': 'fixture-reconnect-01', 'action': 'send_codex_message',
                    'args': {'threadId': TID, 'message': 'ACK only', 'execution': 'headless'}}

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, app):
        with patch.object(bridge, 'checked_app', return_value=app), \
             patch.object(bridge, 'JOURNAL', self.path.parent):
            return bridge.run_job(self.job, self.path)

    def test_concurrent_recovery_coalesces_without_rpc_or_journal_change(self):
        ctx = multiprocessing.get_context('spawn')
        ready, finish, count = ctx.Event(), ctx.Event(), ctx.Value('i', 0)
        owner = ctx.Process(target=owner_process, args=(self.job, str(self.path), ready, finish, count))
        owner.start()
        try:
            self.assertTrue(ready.wait(5), 'fixture turn started')
            before = self.path.read_bytes()
            started = time.monotonic()
            with patch.object(bridge, 'checked_app', side_effect=AssertionError('second RPC forbidden')):
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                    results = list(pool.map(lambda _: bridge.run_job(self.job, self.path), range(5)))
                for result in results:
                    self.assertTrue(result['observation']['coalesced'])
                    self.assertEqual(result['turnId'], 'fixture-turn')
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(self.path.read_bytes(), before)
            conflict = copy.deepcopy(self.job)
            conflict['args']['message'] = 'different task'
            with self.assertRaises(ValueError):
                bridge.run_job(conflict, self.path)
            self.assertEqual(self.path.read_bytes(), before)
        finally:
            finish.set()
            owner.join(10)
        self.assertFalse(owner.is_alive(), 'fixture task finished without cancellation')
        self.assertEqual(owner.exitcode, 0)
        self.assertEqual(count.value, 1)
        with patch.object(bridge, 'checked_app', side_effect=AssertionError('terminal retry must not reconnect')):
            self.assertEqual(bridge.run_job(self.job, self.path)['state'], 'completed')
        self.assertEqual(count.value, 1)

    def test_writer_before_first_journal_is_unknown_and_never_reconnected(self):
        with open(str(self.path) + '.lock', 'a') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(bridge, 'checked_app', side_effect=AssertionError('second RPC forbidden')):
                result = bridge.run_job(self.job, self.path)
            self.assertEqual(result['state'], 'delivery_unknown')
            self.assertFalse(result['targetReceived'])
            self.assertTrue(result['observation']['queryOnly'])
            self.assertFalse(self.path.exists(), 'an observer must not create an authoritative journal')

    def test_conflicting_idle_retry_does_not_overwrite_legitimate_record(self):
        record = {'id': self.job['id'], 'job': self.job, 'state': 'delivery_unknown', 'startIntent': True, 'revision': 3}
        bridge.save(self.path, record)
        before = self.path.read_bytes()
        conflicting = copy.deepcopy(self.job)
        conflicting['args']['message'] = 'not the same payload'
        with self.assertRaises(ValueError):
            bridge.run_job(conflicting, self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_live_approval_and_input_are_classified_then_refused_not_approved(self):
        for method, pending in [('item/commandExecution/requestApproval', 'awaiting_approval'),
                                ('item/permissions/requestApproval', 'awaiting_approval'),
                                ('item/tool/requestUserInput', 'needs_input')]:
            if self.path.exists():
                self.path.unlink()
            app = App(events=[{'id': 71, 'method': method, 'params': {'threadId': TID, 'turnId': 'fixture-turn'}}])
            result = self.fixture(app)
            states = [entry['state'] for entry in result['history']]
            self.assertIn(pending, states)
            self.assertIn('needs_desktop', states)
            self.assertEqual(result['interaction']['status'], 'unavailable')
            self.assertEqual(app.writes, [{'id': 71, 'error': {'code': -32601,
                'message': 'Desktop interaction unavailable in standalone bridge. No action approved.'}}])
            self.assertEqual(result['state'], 'completed')  # Turn ended, not proof of tool execution.
            self.assertFalse(result['requiresUserAction'])

    def test_unrelated_turn_request_does_not_change_our_task_status(self):
        app = App(events=[{'id': 72, 'method': 'item/tool/requestUserInput',
                          'params': {'threadId': TID, 'turnId': 'another-turn'}}])
        result = self.fixture(app)
        self.assertNotIn('needs_input', [entry['state'] for entry in result['history']])
        self.assertNotIn('interaction', result)

    def test_same_thread_other_turn_never_replaces_target_or_reply(self):
        app = App(events=[
            {'method': 'turn/started', 'params': {'threadId': TID, 'turn': {'id': 'other-turn'}}},
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'other-turn',
                'item': {'type': 'agentMessage', 'text': 'UNRELATED REPLY'}}},
            {'method': 'turn/completed', 'params': {'threadId': TID,
                'turn': {'id': 'other-turn', 'status': 'completed'}}},
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'item': {'type': 'agentMessage', 'text': 'ACTUAL REPLY'}}},
        ])
        result = self.fixture(app)
        self.assertEqual(result['turnId'], 'fixture-turn')
        self.assertEqual(result['messages'], ['ACTUAL REPLY'])
        self.assertEqual(result['state'], 'completed')
        self.assertTrue(all(entry.get('turnId') != 'other-turn' for entry in result['history']))

    def test_conflicting_turn_fields_cannot_replace_target_or_supply_reply(self):
        app = App(events=[
            {'method': 'turn/started', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'turn': {'id': 'other-turn'}}},
            {'method': 'turn/started', 'params': {'threadId': TID, 'turnId': 'other-turn',
                'turn': {'id': 'fixture-turn'}}},
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'turn': {'id': 'other-turn'}, 'item': {'type': 'agentMessage', 'text': 'FOREIGN REPLY'}}},
            {'method': 'turn/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'turn': {'id': 'other-turn', 'status': 'completed', 'items': [
                    {'type': 'agentMessage', 'text': 'FOREIGN SNAPSHOT'}]}}},
            {'method': 'turn/completed', 'params': {'threadId': TID, 'turnId': 'other-turn',
                'turn': {'id': 'fixture-turn', 'status': 'completed', 'items': [
                    {'type': 'agentMessage', 'text': 'FOREIGN SNAPSHOT'}]}}},
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'item': {'type': 'agentMessage', 'text': 'ORIGINAL REPLY'}}},
        ])
        result = self.fixture(app)
        self.assertEqual(result['turnId'], 'fixture-turn')
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['messages'], ['ORIGINAL REPLY'])
        self.assertTrue(all(entry.get('turnId') != 'other-turn' for entry in result['history']))

    def test_missing_start_ignores_conflicting_turn_fields_even_with_our_marker(self):
        class Ambiguous(App):
            def call(self, method, args):
                if method == 'turn/start':
                    raise TimeoutError('isolated missing start response')
                return super().call(method, args)

            def event(self, timeout):
                if self.events:
                    return self.events.pop(0)
                raise bridge.Disconnected('isolated fixture connection ended')

        marker = {'type': 'userMessage', 'content': [
            {'type': 'text', 'text': '[dot-request:' + self.job['id'] + ']'}]}
        app = Ambiguous(events=[
            {'method': 'turn/started', 'params': {'threadId': TID, 'turnId': 'other-turn',
                'turn': {'id': 'fixture-turn', 'items': [marker]}}},
            {'method': 'turn/started', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'turn': {'id': 'other-turn', 'items': [marker]}}},
            {'method': 'turn/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'turn': {'id': 'other-turn', 'status': 'completed', 'items': [marker]}}},
        ])
        result = self.fixture(app)
        self.assertEqual(result['state'], 'delivery_unknown')
        self.assertFalse(result['targetReceived'])
        self.assertFalse(result.get('turnId'))
        self.assertFalse(result['retryAutomatically'])

    def test_missing_start_response_recovers_only_matching_user_item(self):
        class LostResponse(App):
            def call(self, method, args):
                if method == 'turn/start':
                    raise bridge.queue.Empty()
                return super().call(method, args)
        app = LostResponse(events=[
            {'method': 'turn/started', 'params': {'threadId': TID, 'turn': {'id': 'other-turn'}}},
            {'method': 'turn/completed', 'params': {'threadId': TID,
                'turn': {'id': 'other-turn', 'status': 'completed'}}},
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'item': {'type': 'userMessage', 'content': [{'type': 'text',
                    'text': '[dot-request:' + self.job['id'] + ']\nACK only'}]}}},
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'item': {'type': 'agentMessage', 'text': 'ACTUAL REPLY'}}},
        ])
        result = self.fixture(app)
        self.assertEqual(result['turnId'], 'fixture-turn')
        self.assertTrue(result['targetReceived'])
        self.assertEqual(result['messages'], ['ACTUAL REPLY'])
        self.assertEqual(result['state'], 'completed')

    def test_unidentified_start_response_never_adopts_other_turn(self):
        class Ambiguous(App):
            def call(self, method, args):
                if method == 'turn/start':
                    raise bridge.queue.Empty()
                return super().call(method, args)
            def event(self, timeout):
                if self.events:
                    return self.events.pop(0)
                raise bridge.Disconnected('isolated fixture connection ended')
        app = Ambiguous(events=[
            {'method': 'turn/started', 'params': {'threadId': TID, 'turn': {'id': 'other-turn'}}},
            {'method': 'turn/completed', 'params': {'threadId': TID,
                'turn': {'id': 'other-turn', 'status': 'completed'}}},
        ])
        result = self.fixture(app)
        self.assertEqual(result['state'], 'delivery_unknown')
        self.assertFalse(result['targetReceived'])
        self.assertFalse(result.get('turnId'))
        self.assertFalse(result['retryAutomatically'])

    def test_completion_snapshot_retains_missed_reply_on_cached_same_request_query(self):
        app = App(events=[{'method': 'turn/completed', 'params': {'threadId': TID,
            'turn': {'id': 'fixture-turn', 'status': 'completed', 'items': [
                {'id': 'reply', 'type': 'agentMessage', 'text': 'RECOVERED ACTUAL REPLY'}]}}}])
        result = self.fixture(app)
        self.assertEqual(result['messages'], ['RECOVERED ACTUAL REPLY'])
        before = self.path.read_bytes()
        with patch.object(bridge, 'checked_app', side_effect=AssertionError('cached query must not restart')):
            cached = bridge.run_job(self.job, self.path)
        self.assertEqual(cached['messages'], result['messages'])
        self.assertEqual(cached['turnId'], 'fixture-turn')
        self.assertEqual(self.path.read_bytes(), before)

    def test_completion_snapshot_preserves_order_and_distinct_identical_replies(self):
        app = App(events=[
            {'method': 'item/completed', 'params': {'threadId': TID, 'turnId': 'fixture-turn',
                'item': {'id': 'second', 'type': 'agentMessage', 'text': 'SAME REPLY'}}},
            {'method': 'turn/completed', 'params': {'threadId': TID,
                'turn': {'id': 'other-turn', 'status': 'completed', 'items': [
                    {'type': 'agentMessage', 'text': 'UNRELATED PRIVATE REPLY'}]}}},
            {'method': 'turn/completed', 'params': {'threadId': TID,
                'turn': {'id': 'fixture-turn', 'status': 'completed', 'items': [
                    {'id': 'first', 'type': 'agentMessage', 'text': 'SAME REPLY'},
                    {'id': 'second', 'type': 'agentMessage', 'text': 'SAME REPLY'},
                    {'id': 'third', 'type': 'agentMessage', 'text': 'LAST REPLY'}]}}},
        ])
        result = self.fixture(app)
        self.assertEqual(result['messages'], ['SAME REPLY', 'SAME REPLY', 'LAST REPLY'])
        self.assertEqual(result['turnId'], 'fixture-turn')
        self.assertEqual(result['state'], 'completed')

    def test_missing_start_and_item_events_recover_from_marked_completed_snapshot(self):
        class LostResponse(App):
            def call(self, method, args):
                if method == 'turn/start':
                    raise bridge.queue.Empty()
                return super().call(method, args)
        app = LostResponse(events=[{'method': 'turn/completed', 'params': {'threadId': TID,
            'turn': {'id': 'fixture-turn', 'status': 'completed', 'items': [
                {'type': 'userMessage', 'content': [{'type': 'text',
                    'text': '[dot-request:' + self.job['id'] + ']\nACK only'}]},
                {'type': 'agentMessage', 'text': 'MATCHED FINAL REPLY'}]}}}])
        result = self.fixture(app)
        self.assertTrue(result['targetReceived'])
        self.assertEqual(result['turnId'], 'fixture-turn')
        self.assertEqual(result['messages'], ['MATCHED FINAL REPLY'])
        self.assertFalse(result['retryAutomatically'])

    def test_not_loaded_during_task_never_infers_completion_or_write_access(self):
        app = App(events=[{'method': 'thread/status/changed',
                          'params': {'threadId': TID, 'status': {'type': 'notLoaded'}}}])
        result = self.fixture(app)
        self.assertEqual(sum(entry['state'] == 'completed' for entry in result['history']), 1)
        self.assertEqual(result['turnId'], 'fixture-turn')
        self.assertTrue(result['targetReceived'])

    def test_observed_approval_flag_and_running_again_remain_distinct(self):
        app = App(events=[
            {'method': 'thread/status/changed', 'params': {'threadId': TID,
                'status': {'type': 'active', 'activeFlags': ['waitingOnApproval']}}},
            {'method': 'thread/status/changed', 'params': {'threadId': TID,
                'status': {'type': 'active', 'activeFlags': []}}},
        ])
        result = self.fixture(app)
        states = [entry['state'] for entry in result['history']]
        waiting = states.index('awaiting_approval')
        self.assertEqual(states[waiting + 1], 'executing')
        self.assertEqual(states[-1], 'completed')
        self.assertFalse(result['requiresUserAction'])


if __name__ == '__main__':
    unittest.main()
