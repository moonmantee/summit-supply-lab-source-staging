import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


def module():
    spec=importlib.util.spec_from_file_location('forensic_migration',Path(__file__).parent/'add-forensics.py')
    value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class MigrationTests(unittest.TestCase):
    def test_participant_writer_updates_answer_line_and_preserves_question_instructions(self):
        migration=module()
        sys.path.insert(0,str(Path(__file__).parent/'probes'))
        import forensics
        from forensic_helpers import SOLUTIONS
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'question.txt'
            for issue,answer in SOLUTIONS.items():
                template=(Path(__file__).parent/'forensic-assets'/('Forensic-Question-%d.txt'%(issue-37))).read_text()
                for value,expected in ((answer,True),('incorrect',False),('',False)):
                    path.write_text(template)
                    subprocess.run([sys.executable,'-c',migration.ANSWER_WRITE_CODE,str(path),value],check=True)
                    self.assertIn('Keep exactly one Answer = line.',path.read_text())
                    self.assertEqual(forensics.check_file(issue,path),expected)

    @unittest.skipUnless(os.name=='posix','Actual Linux directory modes')
    def test_evidence_directory_modes_survive_private_umask(self):
        migration=module()
        with tempfile.TemporaryDirectory() as folder:
            previous=os.umask(0o077)
            try:
                target=Path(folder)/'evidence'/'shop01'; migration.mkdir(target)
            finally: os.umask(previous)
            self.assertEqual(target.stat().st_mode & 0o777,0o755)
            self.assertEqual(target.parent.stat().st_mode & 0o777,0o755)

    @unittest.skipUnless(os.name=='posix','Actual Linux SIGTERM restoration test')
    def test_parent_sigterm_waits_for_child_recovery(self):
        module().run_rehearsal  # Require the recovery-aware operation, not subprocess.run.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); ready=root/'ready'; restored=root/'restored'
            child="import signal,time,sys; from pathlib import Path; signal.signal(signal.SIGTERM,lambda *a:(time.sleep(.2),Path(sys.argv[2]).write_text('restored'),sys.exit(1))); Path(sys.argv[1]).write_text('ready'); time.sleep(30)"
            parent="import importlib.util,signal,sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1]).resolve().parent)); s=importlib.util.spec_from_file_location('migration',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); signal.signal(signal.SIGTERM,m.interrupted); m.run_rehearsal([sys.executable,'-c',sys.argv[2],sys.argv[3],sys.argv[4]],timeout=10)"
            process=subprocess.Popen([sys.executable,'-c',parent,str(Path(__file__).parent/'add-forensics.py'),child,str(ready),str(restored)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and process.poll() is None and time.monotonic()<deadline: time.sleep(.02)
                if process.poll() is not None:
                    _,errors=process.communicate()
                    self.fail('Rehearsal test parent exited before readiness: '+errors.decode(errors='replace'))
                self.assertTrue(ready.exists(),'Rehearsal test child did not become ready')
                process.terminate(); process.communicate(timeout=5)
                self.assertEqual(restored.read_text(),'restored')
                self.assertNotEqual(process.returncode,0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.communicate(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.communicate()
                else: process.communicate()

    def test_second_snapshot_cannot_replace_known_good_archive(self):
        migration=module()
        with tempfile.TemporaryDirectory() as folder:
            migration.BACKUP=Path(folder)
            archive=migration.BACKUP/'production.tar'; archive.write_bytes(b'original rollback')
            with self.assertRaises(RuntimeError): migration.snapshot_production()
            self.assertEqual(archive.read_bytes(),b'original rollback')
