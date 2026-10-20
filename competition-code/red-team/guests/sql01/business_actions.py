"""Scored-service faults; durable journal and passive contestant-repair observation."""
import contextlib
import json
import os
import pathlib
import sqlite3
import time
from first_three_hours import validate_event

STATE=pathlib.Path('/var/lib/summit-caldera-business')

class Actions:
    def __init__(self,path,backend,wall=time.time,mono=time.monotonic,boot=None):
        self.path=pathlib.Path(path);self.backend=backend;self.wall=wall;self.mono=mono
        self.boot=boot or (lambda:pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS recovery(exercise TEXT,event TEXT,action TEXT,created REAL,deadline REAL,mono_deadline REAL,boot TEXT,phase TEXT,PRIMARY KEY(exercise,event))')
        if os.name=='posix':self.path.chmod(0o600)
    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def status(self):
        with self.connect() as db:return [dict(row) for row in db.execute('SELECT * FROM recovery ORDER BY rowid')]
    def ready(self):
        return all(row['phase'] in ('RESTORED','REPAIRED') for row in self.status()) and self.backend.ready()
    def apply(self,event):
        validate_event(event,self.wall())
        with self.connect() as db:
            if db.execute("SELECT 1 FROM recovery WHERE phase NOT IN ('RESTORED','REPAIRED')").fetchone():raise ValueError('Outstanding fault or conflict')
            if db.execute('SELECT 1 FROM recovery WHERE exercise=? AND event=?',(event['exercise'],event['id'])).fetchone():raise ValueError('Duplicate action')
            if db.execute('SELECT count(*) FROM recovery').fetchone()[0]>=1000:raise ValueError('Recovery record limit reached')
            if not self.backend.ready():raise ValueError('Business baseline unavailable')
            validate_event(event,self.wall())
            db.execute('INSERT INTO recovery VALUES(?,?,?,?,?,?,?,?)',(event['exercise'],event['id'],event['action'],self.wall(),
                self.wall()+event['duration'],self.mono()+event['duration'],self.boot(),'PREPARED'))
        # PREPARED is committed before the first mutation; restart/offline recovery
        # handles a crash after any partial native operation.
        with self.connect() as db:
            # The second transaction holds the same cross-process SQLite writer
            # lock as recover(). Durable PREPARED remains after a crash/failure,
            # while recovery cannot race an in-flight native mutation.
            row=db.execute('SELECT phase FROM recovery WHERE exercise=? AND event=?',(event['exercise'],event['id'])).fetchone()
            if row['phase']!='PREPARED':raise ValueError('Action already recovered')
            validate_event(event,self.wall())
            self.backend.apply(event['action'],event['expires'])
            db.execute("UPDATE recovery SET phase='APPLIED' WHERE exercise=? AND event=? AND phase='PREPARED'",(event['exercise'],event['id']))
        return {'outcome':'APPLIED'}
    def recover(self):
        # Historical CLI/unit name retained for installation compatibility.
        # This path NEVER starts a service or restores its startup/restart policy.
        # Timings are dispatch reservations only, not service-repair deadlines.
        with self.connect() as db:
            for record in db.execute("SELECT * FROM recovery WHERE phase IN ('PREPARED','APPLIED')").fetchall():
                try:
                    repaired=self.backend.observe_repair()
                except Exception:continue  # Preserve contestant changes and hold future dispatch.
                if repaired is True:
                    db.execute("UPDATE recovery SET phase='REPAIRED' WHERE exercise=? AND event=?",(record['exercise'],record['event']))

def main():
    import argparse
    import socket
    if socket.gethostname()=='sql01':from mariadb_backend import MariaDB as Backend,private_state
    elif socket.gethostname()=='shop01':from apache_backend import Apache as Backend,private_state
    else:raise ValueError('Unapproved native recovery host')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('recover','status'))
    args=parser.parse_args()
    if os.geteuid()!=0:raise ValueError('Organizer/root recovery required')
    private_state()
    actions=Actions(STATE/'recovery.sqlite3',Backend())
    if args.command=='recover':actions.recover()
    else:print(json.dumps(actions.status()))

if __name__=='__main__':main()
