import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'device'))
from executable import Executable, resolve_executable
from reliability import BridgeFault, error_info
from transport import AppServer


class ExecutableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = {'PATH': str(self.root / 'bin')}
        self.apps = [self.root / 'Applications']
        self.legacy = self.apps[0] / 'ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
        self.modern = self.apps[0] / 'Codex.app/Contents/Resources/codex'

    def tearDown(self):
        self.tmp.cleanup()

    def program(self, path, version='0.162.0-alpha.2', body=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\n' + (body or 'printf "codex-cli ' + version + '\\n"\n'))
        path.chmod(0o700)
        return path

    def resolve(self, **kw):
        # Only fixture candidates; never inspect the user's installed programs.
        return resolve_executable(environ=self.env, home=self.root, app_roots=self.apps, package_roots=[], **kw)

    def test_upgrade_rediscovers_moved_app_on_next_connection(self):
        self.program(self.legacy)
        self.assertEqual(self.resolve().path, str(self.legacy))
        self.legacy.unlink()
        self.program(self.modern, '0.163.1')
        result = self.resolve()
        self.assertEqual(result.path, str(self.modern))
        self.assertEqual(result.version, '0.163.1')

    def test_path_installation_is_used_after_stale_app_paths(self):
        target = self.program(self.root / 'bin/codex')
        result = self.resolve()
        self.assertEqual(result.path, str(target))
        self.assertEqual(result.source, 'path')

    def test_broken_explicit_override_never_falls_back(self):
        self.program(self.modern)
        self.env['DOT_CODEX_EXECUTABLE'] = str(self.root / 'missing/codex')
        with self.assertRaises(BridgeFault) as exc:
            self.resolve()
        self.assertEqual(exc.exception.code, 'CODEX_EXECUTABLE_OVERRIDE_INVALID')

    def test_explicit_override_takes_precedence(self):
        chosen = self.program(self.root / 'selected/codex', '0.170.0')
        self.program(self.legacy)
        self.env['DOT_CODEX_EXECUTABLE'] = str(chosen)
        result = self.resolve()
        self.assertEqual(result.path, str(chosen))
        self.assertEqual(result.source, 'explicit_override')

    def test_relative_override_and_relative_path_entries_not_executed(self):
        self.env['DOT_CODEX_EXECUTABLE'] = './codex'
        with self.assertRaises(BridgeFault):
            self.resolve()
        self.env = {'PATH': 'relative::.'}
        with patch('executable.subprocess.run', side_effect=AssertionError('must not spawn cwd')):
            with self.assertRaises(BridgeFault):
                self.resolve()

    def test_wrong_program_or_non_executable_is_skipped(self):
        self.program(self.legacy, body='printf "not Codex\\n"\n')
        self.program(self.modern).chmod(0o600)
        target = self.program(self.root / 'bin/codex')
        self.assertEqual(self.resolve().path, str(target))

    def test_symlinks_are_probed_only_once(self):
        target = self.program(self.legacy, body='printf "unrecognized\\n"\n')
        self.modern.parent.mkdir(parents=True)
        self.modern.symlink_to(target)
        with patch('executable.subprocess.run', wraps=subprocess.run) as runner:
            with self.assertRaises(BridgeFault):
                self.resolve()
            self.assertEqual(runner.call_count, 1)

    def test_hung_version_probe_has_bounded_timeout_and_safe_error(self):
        self.program(self.legacy, body='exec sleep 2\n')
        with self.assertRaises(BridgeFault) as exc:
            self.resolve(probe_timeout=.05, budget_seconds=.05)
        info = error_info(exc.exception)
        self.assertEqual(info['code'], 'CODEX_EXECUTABLE_UNUSABLE')
        self.assertTrue(info['requiresUserAction'])
        self.assertNotIn(str(self.root), str(info))

    def test_missing_path_reports_actionable_classification(self):
        with self.assertRaises(BridgeFault) as exc:
            self.resolve()
        self.assertEqual(exc.exception.code, 'CODEX_EXECUTABLE_NOT_FOUND')

    def test_spawn_upgrade_race_retries_only_before_initialize(self):
        first = Executable('/fixture/old/codex', 'app_bundle', '0.162.0')
        second = Executable('/fixture/new/codex', 'app_bundle', '0.163.0')
        proc = MagicMock()
        with patch('transport.resolve_executable', side_effect=[first, second]), \
             patch('transport.subprocess.Popen', side_effect=[FileNotFoundError(), proc]) as spawn, \
             patch('transport.threading.Thread'), patch.object(AppServer, 'call', return_value={}) as rpc, \
             patch.object(AppServer, 'write'):
            app = AppServer()
            self.assertEqual([call.args[0][0] for call in spawn.call_args_list], [first.path, second.path])
            self.assertEqual(rpc.call_count, 1)
            self.assertEqual(rpc.call_args.args[0], 'initialize')
            app.close()


if __name__ == '__main__':
    unittest.main()
