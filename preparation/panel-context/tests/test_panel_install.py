import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
try:
    from install_panel import validate_package,backup_files,publish_files,restore_files
except ImportError: validate_package=backup_files=publish_files=restore_files=None


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(validate_package,'guarded installer missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)/'root';self.package=pathlib.Path(self.tmp.name)/'package';self.backup=pathlib.Path(self.tmp.name)/'backup'
        self.dest=self.root/'opt/summit-caldera-fixtures/fixture_control.py';self.dest.parent.mkdir(parents=True);self.dest.write_text('old')
        self.package.mkdir();(self.package/'new.py').write_text('new')
        digest=lambda data:hashlib.sha256(data.encode()).hexdigest()
        self.manifest={'version':1,'files':[{'source':'new.py','destination':'/opt/summit-caldera-fixtures/fixture_control.py','sha256':digest('new'),'predecessor':digest('old')}],'dependencies':[]}
        self.save()
    def save(self):
        data=json.dumps(self.manifest).encode();(self.package/'release-manifest.json').write_bytes(data);self.hash=hashlib.sha256(data).hexdigest()
    def validate(self,host='red01'):return validate_package(self.package,self.hash,self.root,host)

    def test_wrong_host_and_predecessor_rejected(self):
        with self.assertRaises(ValueError):self.validate('score01')
        self.dest.write_text('unknown')
        with self.assertRaises(ValueError):self.validate()
        self.assertEqual(self.dest.read_text(),'unknown')

    def test_package_hash_and_destination_escape_rejected(self):
        (self.package/'new.py').write_text('changed')
        with self.assertRaises(ValueError):self.validate()
        (self.package/'new.py').write_text('new');self.manifest['files'][0]['destination']='/opt/summit-caldera-fixtures/../../etc/passwd';self.save()
        with self.assertRaises(ValueError):self.validate()

    def test_existing_nonregular_new_destination_rejected(self):
        if sys.platform=='win32':self.skipTest('Linux FIFO required')
        import os
        self.dest.unlink();os.mkfifo(self.dest);self.manifest['files'][0]['predecessor']=None;self.save()
        with self.assertRaises(ValueError):self.validate()

    def test_payload_change_after_preflight_rejected(self):
        manifest=self.validate();(self.package/'new.py').write_text('concurrent new payload')
        with self.assertRaises(ValueError):publish_files(manifest,self.package,self.root)
        self.assertEqual(self.dest.read_text(),'old')

    def test_credential_verification_is_semantic_and_detects_changes(self):
        import install_panel
        self.assertTrue(hasattr(install_panel,'credential_fingerprint'),'credential checks still depend on YAML formatting')
        cred=self.package/'credentials.json';runtime=self.package/'summit.yml'
        cred.write_text('{"username":"organizer","password":"secret","red_api_key":"red","blue_api_key":"blue"}')
        runtime.write_text('users:\n  red:\n    organizer: hashed-secret\napi_key_red: hashed-red\nplugins: [magma]\n')
        original=install_panel.credential_fingerprint(cred,runtime)
        runtime.write_text('plugins:\n- magma\napi_key_red: hashed-red\nusers: {red: {organizer: hashed-secret}}\n')
        self.assertEqual(install_panel.credential_fingerprint(cred,runtime),original)
        cred.write_text('{"username":"organizer","password":"changed","red_api_key":"red","blue_api_key":"blue"}')
        self.assertNotEqual(install_panel.credential_fingerprint(cred,runtime),original)

    def test_backup_publish_restore_and_unknown_replacement(self):
        manifest=self.validate();backup_files(manifest,self.backup,self.root);publish_files(manifest,self.package,self.root)
        self.assertEqual(self.dest.read_text(),'new')
        self.dest.write_text('organizer replacement')
        with self.assertRaises(ValueError):restore_files(manifest,self.backup,self.root)
        self.assertEqual(self.dest.read_text(),'organizer replacement')
        self.dest.write_text('new');restore_files(manifest,self.backup,self.root)
        self.assertEqual(self.dest.read_text(),'old')

    def test_symlink_destination_rejected(self):
        if sys.platform=='win32':self.skipTest('Linux symlinks required')
        self.dest.unlink();self.dest.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):self.validate()

    def test_low_disk_and_backup_failure_preserve_original(self):
        with patch('install_panel.shutil.disk_usage',return_value=SimpleNamespace(free=256*1024*1024-1)),self.assertRaises(ValueError):self.validate()
        manifest=self.validate();write_bytes=pathlib.Path.write_bytes
        def full(path,data):
            if path.parent==self.backup:raise OSError('disk full')
            return write_bytes(path,data)
        with patch.object(pathlib.Path,'write_bytes',full),self.assertRaises(OSError):backup_files(manifest,self.backup,self.root)
        self.assertEqual(self.dest.read_text(),'old')

    def test_rollback_after_new_writes_archives_database(self):
        if sys.platform=='win32':self.skipTest('Linux ownership restore required')
        from rollback_panel import rollback
        from install_panel import snapshot_database
        database=self.root/'var/lib/summit-caldera-fixtures/state.db';database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as db:db.execute('CREATE TABLE history(value TEXT)');db.execute("INSERT INTO history VALUES('original')")
        manifest=self.validate();backup_files(manifest,self.backup,self.root);snapshot_database(database,self.backup/'state-before.sqlite3')
        publish_files(manifest,self.package,self.root)
        info=database.stat();(self.backup/'deployment.json').write_text(json.dumps(dict(manifest=manifest,config_state='/var/lib/summit-caldera-fixtures/state.db',db_uid=info.st_uid,db_gid=info.st_gid,db_mode=0o600)))
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE panel_admin_audit(value TEXT)');db.execute("INSERT INTO panel_admin_audit VALUES('organizer saved')")
            db.execute('CREATE TABLE panel_revisions(value TEXT)');db.execute("INSERT INTO panel_revisions VALUES('new revision')")
        with patch('rollback_panel.run'),self.assertRaises(ValueError):rollback(self.backup,automatic=True,filesystem=self.root)
        self.assertEqual(self.dest.read_text(),'new')
        with patch('rollback_panel.run'):result=rollback(self.backup,filesystem=self.root)
        self.assertEqual(self.dest.read_text(),'old')
        exported=json.loads((pathlib.Path(result['archive'])/'profiles-snapshots-audit.json').read_text())
        self.assertEqual(exported['panel_revisions'],[{'value':'new revision'}])
        with sqlite3.connect(database) as db:self.assertEqual(db.execute('SELECT value FROM history').fetchone()[0],'original')

if __name__=='__main__':unittest.main()
