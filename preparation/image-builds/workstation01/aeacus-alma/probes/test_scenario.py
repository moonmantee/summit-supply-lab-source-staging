import tempfile
import unittest
from pathlib import Path
from scenario import scan_clean, answers_correct, account_disabled


class ScenarioTests(unittest.TestCase):
    def test_renamed_content_is_still_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'renamed.txt'
            p.write_bytes(b'prefix SUMMIT-TRAINING-CREDENTIALS suffix')
            self.assertFalse(scan_clean([d], [b'SUMMIT-TRAINING-CREDENTIALS']))
            p.unlink()
            self.assertTrue(scan_clean([d], [b'SUMMIT-TRAINING-CREDENTIALS']))

    def test_missing_root_or_scan_error_does_not_award_points(self):
        self.assertFalse(scan_clean(['/does/not/exist'], [b'marker']))

    def test_symlinked_artifact_is_detected_without_ignoring_it(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'payload'
            p.write_bytes(b'marker')
            try:
                (Path(d)/'renamed').symlink_to(p)
            except OSError as error:
                if getattr(error,'winerror',None)==1314:
                    self.skipTest('Windows symlink privilege unavailable; run on AlmaLinux')
                raise
            self.assertFalse(scan_clean([d], [b'marker']))

    def test_cross_chunk_content_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'large').write_bytes(b'x'*(65536-2)+b'marker')
            self.assertFalse(scan_clean([d], [b'marker']))

    def test_answer_requires_one_explicit_value(self):
        self.assertTrue(answers_correct('Q1 = trainer\nQ2 = timer /path\n',1,'trainer'))
        self.assertFalse(answers_correct('Q1 = trainer\nQ1 = other\n',1,'trainer'))
        self.assertFalse(answers_correct('Q1 = trainer extra\n',1,'trainer'))
        self.assertFalse(answers_correct(None,1,'trainer'))

    def test_question_file_scores_only_its_own_answer_section(self):
        from scenario import question_answer_correct
        self.assertTrue(question_answer_correct('Forensic Question 1\nWho created the task?\n\nAnswer = trainer\n','trainer'))
        for text in ('Answer =\n','trainer\nAnswer = wrong\n','Q1 = trainer\n','Answer = trainer\nAnswer = wrong\n','Answer = trainer extra\n'):
            self.assertFalse(question_answer_correct(text,'trainer'))
        self.assertFalse(question_answer_correct(None,'trainer'))

    def test_password_lock_alone_does_not_disable_key_or_desktop_login(self):
        self.assertFalse(account_disabled({'exists':True,'locked':True,'expired':False,'shell':'/bin/bash','keys_absent':False},True))
        valid={'exists':True,'locked':True,'expired':True,'shell':'/sbin/nologin','keys_absent':True}
        self.assertTrue(account_disabled(valid,True))
        self.assertFalse(account_disabled({'exists':False},True))
        self.assertTrue(account_disabled({'exists':False},False))
        self.assertFalse(account_disabled({},False))


if __name__=='__main__':
    unittest.main()
