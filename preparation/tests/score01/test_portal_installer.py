"""Exercise the actual installer health function with deterministic curl responses."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

class InstallerTests(unittest.TestCase):
    def run_health(self,success):
        source=(Path(__file__).parent/'portal-install.sh').read_text()
        match=re.search(r'wait_portal\(\) \{.*?\n\}',source,re.S)
        self.assertIsNotNone(match,'Installer must wait for Nginx workers after reload')
        bash=Path('C:/Program Files/Git/bin/bash.exe')
        if not bash.exists(): bash=Path('/bin/bash')
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'check.sh'
            script.write_text('set -eu\ncount_file='+"'"+str(Path(tmp)/'count').replace('\\','/')+"'"+'\n'+
                "curl() { local n=0; if [[ -f $count_file ]]; then read -r n < \"$count_file\"; fi; n=$((n+1)); echo \"$n\" > \"$count_file\"; "+
                ('if [[ $n == 1 ]]; then printf 404; else printf 200; fi;' if success else 'printf 404;')+' }\n'+
                'sleep() { :; }\n'+match[0]+'\nwait_portal http://10.77.70.10:8080/portal/\n',encoding='utf-8',newline='\n')
            result=subprocess.run([str(bash),str(script)],capture_output=True,text=True)
            calls=int((Path(tmp)/'count').read_text())
            return result,calls

    def test_transient_404_after_reload_is_retried(self):
        result,calls=self.run_health(True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(calls,2)

    def test_persistent_failure_still_triggers_rollback(self):
        result,calls=self.run_health(False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,10)

if __name__=='__main__': unittest.main()
