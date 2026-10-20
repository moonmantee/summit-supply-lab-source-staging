from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from test_portal import scoring_fixture
from portal_store import PortalStore

class UpgradeTests(unittest.TestCase):
    def exercise(self,stop_fails=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); score=root/'summit-scoring'; portal=root/'summit-portal'; stage=root/'team-portal-package'
            (score/'state').mkdir(parents=True); stage.mkdir(); (stage/'SHA256SUMS.json').write_text('{}')
            scoredb=score/'state/results.sqlite3'; scoring_fixture(scoredb,state='STOPPED')
            with closing(sqlite3.connect(scoredb)) as db,db: db.execute('CREATE TABLE scoring_rounds(id INTEGER)')
            PortalStore(portal/'portal-state/portal.sqlite3',scoredb)
            attachments=portal/'portal-state/files/attachments'; attachments.mkdir(parents=True)
            sentinel=attachments/'original-resource'; sentinel.write_bytes(b'Keep this private resource')
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if stop_fails and 'stop' in args: raise subprocess.CalledProcessError(1,args)
                return subprocess.CompletedProcess(args,0)
            source=(Path(__file__).parent/'update_six_injects.py').read_text().replace('/home/jwang',str(root).replace('\\','/'))
            with patch('subprocess.run',side_effect=run),patch('shutil.copytree',side_effect=OSError('Backup storage unavailable')):
                with self.assertRaises((OSError,subprocess.CalledProcessError)): exec(compile(source,'updater-under-test','exec'),{})
            self.assertEqual(sentinel.read_bytes(),b'Keep this private resource')
            self.assertTrue((portal/'portal-state/portal.sqlite3').exists())
            starts=[args[-1] for args in calls if 'start' in args]
            self.assertEqual(starts,['summit-team-portal.service','summit-check.timer'])

    def test_failed_attachment_backup_keeps_originals_and_restores_services(self): self.exercise()
    def test_partial_stop_failure_still_restores_prior_services(self): self.exercise(stop_fails=True)

if __name__=='__main__': unittest.main()
