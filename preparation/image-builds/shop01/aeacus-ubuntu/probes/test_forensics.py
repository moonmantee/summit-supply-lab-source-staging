import tempfile
import unittest
from pathlib import Path
import forensics


class ForensicTests(unittest.TestCase):
    def test_blank_wrong_duplicate_and_answer_in_question_never_score(self):
        for text in ('Question mentions 198.51.100.77\nAnswer =\n',
                     'Answer = 198.51.100.78\n','Answer = 198.51.100.77\nAnswer = wrong\n',
                     'Answer = 198.51.100.77 extra\n'):
            self.assertFalse(forensics.evaluate(38,text))

    def test_exact_answers_allow_surrounding_whitespace(self):
        for issue,answer in ((38,'198.51.100.77'),(39,'/training-fixtures/public-backup.sql'),
                             (40,'summit-shop-marker.service')):
            self.assertTrue(forensics.evaluate(issue,'Question\nAnswer = '+answer+'  \n'))
        self.assertFalse(forensics.evaluate(39,'Answer = /TRAINING-FIXTURES/public-backup.sql\n'))

    def test_missing_symlink_large_and_nonregular_answers_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'answer'
            self.assertFalse(forensics.check_file(38,path))
            path.mkdir(); self.assertFalse(forensics.check_file(38,path)); path.rmdir()
            target=Path(folder)/'target'; target.write_text('Answer = 198.51.100.77\n')
            try: path.symlink_to(target)
            except OSError: pass
            else: self.assertFalse(forensics.check_file(38,path)); path.unlink()
            path.write_text('Answer = 198.51.100.77\n'+'x'*20000)
            self.assertFalse(forensics.check_file(38,path))


if __name__=='__main__': unittest.main()
