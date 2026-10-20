import tempfile
import unittest
from pathlib import Path
from recovery_state import ensure_directory,preserve_file


class RecoveryStateTests(unittest.TestCase):
    def test_partial_preparation_can_resume_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'recovery'
            ensure_directory(root)
            preserve_file(root/'installed-before.txt',b'original packages\n')
            ensure_directory(root)
            preserve_file(root/'installed-before.txt',b'original packages\n')
            with self.assertRaises(ValueError):
                preserve_file(root/'installed-before.txt',b'different packages\n')
            self.assertEqual((root/'installed-before.txt').read_bytes(),b'original packages\n')

    def test_collision_is_not_treated_as_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'collision'
            p.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                ensure_directory(p)
            self.assertEqual(p.read_bytes(),b'keep')


if __name__=='__main__':
    unittest.main()
