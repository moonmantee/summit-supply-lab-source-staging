"""Local rollback archives panel revisions/evidence before restoring compatibility."""
import argparse
import json
import os
import pathlib
import sqlite3
import sys
import time
import uuid
from install_panel import UNITS,atomic_bytes,run,snapshot_database,restore_files,safe_path


def automatic_allowed(database):
    with sqlite3.connect(database) as db:
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='panel_admin_audit'").fetchone()
        return not exists or db.execute('SELECT count(*) FROM panel_admin_audit').fetchone()[0]==0


def archive_state(database,archive):
    archive.mkdir(mode=0o700)
    snapshot_database(database,archive/'state-after.sqlite3')
    with sqlite3.connect(database) as db:
        db.row_factory=sqlite3.Row;exports={}
        for table in ('panel_profiles','panel_revisions','panel_snapshots','panel_admin_audit'):
            if db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
                exports[table]=[dict(row) for row in db.execute('SELECT * FROM '+table)]
    (archive/'profiles-snapshots-audit.json').write_text(json.dumps(exports));os.chmod(archive/'profiles-snapshots-audit.json',0o600)


def rollback(backup,automatic=False,filesystem=pathlib.Path('/')):
    deployment=json.loads((backup/'deployment.json').read_text());database=safe_path(filesystem,deployment['config_state'])
    for unit in UNITS:run('systemctl','stop',unit)
    archive=backup/('after-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    archive_state(database,archive)
    if automatic and not automatic_allowed(database): raise ValueError('New organizer writes preserved; automatic rollback refused. Services stopped; archive: '+str(archive))
    restore_files(deployment['manifest'],backup,filesystem)
    atomic_bytes(database,(backup/'state-before.sqlite3').read_bytes(),deployment['db_mode'],(deployment['db_uid'],deployment['db_gid']))
    run('systemctl','daemon-reload')
    for unit in reversed(UNITS):run('systemctl','start',unit)
    return {'rollback':'PASS','archive':str(archive)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backup',required=True);args=parser.parse_args()
    if os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='red01':raise ValueError('Local red01 root required')
    if pathlib.Path(args.backup).name!=args.backup:raise ValueError('Use the backup ID only')
    backup=pathlib.Path('/var/backups/ccdc-panel')/args.backup
    if backup.is_symlink() or not backup.is_dir():raise ValueError('Unknown backup')
    print(json.dumps(rollback(backup)))

if __name__=='__main__':main()
