"""Installer preservation, rollback, and failure recovery without live systemd."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import shop_probe_installer as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = 'def run_probe(config):\n    try:\n        return ("PASS", "legacy")\n    except Exception:\n        raise\n'
        (self.base/'scorer.py').write_text(self.source)
        (self.base/'config.json').write_text(json.dumps({'services': [
            {'id': 'shop01-https', 'probe': 'https', 'url': 'https://shop.test/'}]}))
        (self.base/'results.sqlite3').write_bytes(b'existing score history sentinel')
        self.module = Path(__file__).with_name('shop_probe.py').read_text()

    def run_installer(self, *args, fail_import=False, timer='active'):
        calls = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['installer', '--base', str(self.base), *args]))
            stack.enter_context(patch.object(os, 'geteuid', return_value=1000, create=True))
            stack.enter_context(patch.object(installer, 'state', side_effect=lambda u: timer if u.endswith('.timer') else 'inactive'))
            stack.enter_context(patch.object(installer, 'ctl', side_effect=lambda *a, **kw: calls.append(a)))
            stack.enter_context(patch.object(sys, 'path', list(sys.path)))
            if fail_import:
                stack.enter_context(patch.object(installer.importlib.util, 'spec_from_file_location', side_effect=RuntimeError('fixture import failure')))
            result = installer.main(self.module)
        return result, calls

    def test_install_and_rollback_preserve_config_and_score_history(self):
        config = (self.base/'config.json').read_bytes()
        history = (self.base/'results.sqlite3').read_bytes()
        result, calls = self.run_installer()
        self.assertEqual(result, 0)
        self.assertIn('return shop_probe(config)', (self.base/'scorer.py').read_text())
        self.assertEqual((self.base/'shop_probe.py').read_text(), self.module)
        self.assertEqual(calls, [('stop', 'summit-check.timer'), ('start', 'summit-check.timer')])
        backup, = (self.base/'backups').iterdir()
        self.run_installer('--rollback', str(backup))
        self.assertEqual((self.base/'scorer.py').read_text(), self.source)
        self.assertFalse((self.base/'shop_probe.py').exists())
        self.assertEqual((self.base/'config.json').read_bytes(), config)
        self.assertEqual((self.base/'results.sqlite3').read_bytes(), history)

    def test_import_failure_restores_previous_files(self):
        (self.base/'shop_probe.py').write_text('# previous probe')
        with self.assertRaisesRegex(RuntimeError, 'fixture import failure'):
            self.run_installer(fail_import=True)
        self.assertEqual((self.base/'scorer.py').read_text(), self.source)
        self.assertEqual((self.base/'shop_probe.py').read_text(), '# previous probe')

    def test_stopped_timer_stays_stopped(self):
        result, calls = self.run_installer(timer='inactive')
        self.assertEqual(result, 0)
        self.assertEqual(calls, [('stop', 'summit-check.timer')])

    def test_unknown_scorer_is_rejected_before_changes(self):
        with self.assertRaisesRegex(ValueError, 'Unrecognized scorer'):
            installer.patched('def different_scorer(): pass')

    def test_patch_is_idempotent(self):
        once = installer.patched(self.source)
        self.assertEqual(installer.patched(once), once)


if __name__ == '__main__':
    unittest.main()
