import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

@unittest.skipUnless(os.name=='posix','Actual Bash permission rehearsal runs on Ubuntu')
class StageRollbackTests(unittest.TestCase):
    def test_nested_function_failure_restores_original_mode_and_exits(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'fixture'; target.write_text('fixture'); target.chmod(0o750)
            code='set -euo pipefail; source "$1"; target=$2; rollback(){ chmod 750 "$target"; }; enable_rollback_trap; boom(){ chmod 777 "$target"; touch "$target.planted"; false; }; boom; touch "$target.after"'
            p=subprocess.run(['bash','-c',code,'test',str(Path(__file__).parent/'stage_common.sh'),str(target)],capture_output=True,text=True)
            self.assertEqual(p.returncode,1,p.stderr)
            self.assertTrue(Path(str(target)+'.planted').exists(),'Failure must occur after fixture mutation, not while sourcing the helper')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o750)
            self.assertFalse(Path(str(target)+'.after').exists())

    def test_rollback_failure_reports_distinct_status(self):
        code='set -euo pipefail; source "$1"; rollback(){ return 1; }; enable_rollback_trap; boom(){ false; }; boom'
        p=subprocess.run(['bash','-c',code,'test',str(Path(__file__).parent/'stage_common.sh')],capture_output=True,text=True)
        self.assertEqual(p.returncode,90)
        self.assertIn('ROLLBACK FAILED',p.stderr)

if __name__=='__main__': unittest.main()
