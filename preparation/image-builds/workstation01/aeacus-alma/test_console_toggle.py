import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest


class ConsoleToggleTests(unittest.TestCase):
    def module(self):
        filename = Path(__file__).with_name('console_toggle.py')
        self.assertTrue(filename.exists(), 'Console helper is not implemented')
        spec = importlib.util.spec_from_file_location('console_toggle', filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_interface_adapter_uses_actual_device_and_rejects_invalid_names(self):
        m = self.module()
        namespace = {}
        exec(m.adapt_interface('def device(): return "ens160"', 'enp6s18'), namespace)
        self.assertEqual(namespace['device'](), 'enp6s18')
        for name in ('', '../bad', 'eth0;reboot', 'eth0\n'):
            with self.assertRaises(ValueError):
                m.adapt_interface('ens160', name)

    def test_report_requires_fresh_complete_exact_score(self):
        m = self.module()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            report = Path(temporary) / 'report.html'
            report.write_text('100 out of 100 points received</html>')
            self.assertFalse(m.report_matches(report, 0, 0))
            self.assertTrue(m.report_matches(report, 100, 0))
            self.assertFalse(m.report_matches(report, 100, time.time() + 10))
            report.write_text('100 out of 100 points received')
            self.assertFalse(m.report_matches(report, 100, 0))

    def test_answers_preserve_questions_and_replace_only_answer_line(self):
        m = self.module()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            (root / 'Forensic-Question-1.txt').write_text('Evidence instructions\nAnswer = \n')
            m.fill_answers(root, {17: (1, 'example-answer')})
            self.assertEqual((root / 'Forensic-Question-1.txt').read_text(),
                             'Evidence instructions\nAnswer = example-answer\n')

    def test_missing_answer_placeholder_refuses_to_write(self):
        m = self.module()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            file = root / 'Forensic-Question-1.txt'
            file.write_text('Unexpected question format\n')
            with self.assertRaises(RuntimeError):
                m.fill_answers(root, {17: (1, 'example-answer')})
            self.assertEqual(file.read_text(), 'Unexpected question format\n')

    def test_new_cycle_and_failed_capture_preserve_previous_recovery(self):
        m = self.module()
        self.assertTrue(hasattr(m, 'allocate_session'), 'Retryable session allocation is missing')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            first = m.allocate_session(root, None)
            (first / 'original').write_text('retained recovery')
            second = m.allocate_session(root, {'phase': 'reset'})
            third = m.allocate_session(root, {'phase': 'capture-failed'})
            fourth = m.allocate_session(root, {'phase': 'capturing'})
            self.assertEqual(len({first, second, third, fourth}), 4)
            self.assertEqual((first / 'original').read_text(), 'retained recovery')

    def test_active_recovery_cannot_be_overwritten_by_another_solve(self):
        m = self.module()
        self.assertTrue(hasattr(m, 'allocate_session'), 'Session recovery gate is missing')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            for phase in ('ready', 'solved', 'recovery-needed', 'unknown'):
                with self.assertRaises(RuntimeError):
                    m.allocate_session(root, {'phase': phase})
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
