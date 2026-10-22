"""Reply progress during replay; no runtime journal or cloud connections."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'device'))
import agent


class ReplayTests(unittest.TestCase):
    def test_fresh_completion_precedes_backlog_while_old_records_still_replay(self):
        records = [(None, {'id': 'old-' + str(n), 'revision': 2,
                    'state': 'completed', 'updated': n}) for n in range(20)]
        records.append((None, {'id': 'fresh-reply', 'revision': 7,
                        'state': 'completed', 'updated': 1000}))
        before = copy.deepcopy(records)
        pushed, synced = [], {}
        with patch.object(agent, 'rpc', side_effect=lambda config, data: pushed.append(data['record']['id'])):
            self.assertEqual(agent.sync_batch(records, {}, synced), 6)
            self.assertEqual(pushed[0], 'fresh-reply')
            while len(synced) < len(records):
                self.assertGreater(agent.sync_batch(records, {}, synced), 0)
        self.assertEqual(len(pushed), len(records))
        self.assertEqual(set(pushed), {r['id'] for _, r in records})
        self.assertEqual(records, before)

    def test_new_revision_is_prioritized_and_failed_push_is_not_marked_synced(self):
        old = {'id': 'old-result', 'revision': 2, 'state': 'completed', 'updated': 1}
        fresh = {'id': 'current-task', 'revision': 8, 'state': 'executing', 'updated': 2}
        synced = {'current-task': 7}
        with patch.object(agent, 'rpc', side_effect=TimeoutError('isolated transport fault')):
            with self.assertRaises(TimeoutError):
                agent.sync_batch([(None, old), (None, fresh)], {}, synced)
        self.assertEqual(synced, {'current-task': 7})
        with patch.object(agent, 'rpc') as rpc:
            self.assertEqual(agent.sync_batch([(None, old), (None, fresh)], {}, synced, max_records=1), 1)
            self.assertEqual(rpc.call_args.args[1]['record']['id'], 'current-task')
        self.assertEqual(synced, {'current-task': 8})


if __name__ == '__main__':
    unittest.main()
