import subprocess
import sys
import unittest
from pathlib import Path

class DispatcherTests(unittest.TestCase):
    def test_unknown_objective_never_prints_pass(self):
        p=subprocess.run([sys.executable,str(Path(__file__).parent/'check.py'),'999'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(p.stdout.strip(),'ERROR')

    def test_unauthorized_account_absence_is_read_only(self):
        import check
        self.assertEqual(set(check.registry()),set(range(1,41)))

if __name__=='__main__': unittest.main()
