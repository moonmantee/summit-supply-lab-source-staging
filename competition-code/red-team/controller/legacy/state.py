import contextlib
import os
import pathlib
import sqlite3
import uuid


class Store:
    def __init__(self, path):
        self.path = pathlib.Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == 'posix':
            os.chmod(self.path.parent, 0o700)
        with self.transaction() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS exercises(
                  id TEXT PRIMARY KEY, scoring_event_id INTEGER NOT NULL,
                  state TEXT NOT NULL, elapsed REAL NOT NULL DEFAULT 0,
                  last_tick REAL, duration REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS dispatch(
                  exercise TEXT, event TEXT, guest TEXT, outcome TEXT, expires REAL,
                  PRIMARY KEY(exercise,event));
                CREATE TABLE IF NOT EXISTS audit(
                  id INTEGER PRIMARY KEY, exercise TEXT, event TEXT, outcome TEXT);
            ''')
        if os.name == 'posix':
            os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def transaction(self):
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def create_exercise(self, scoring_event_id, duration_s=12600):
        if type(scoring_event_id) is not int or scoring_event_id < 1 or duration_s not in (10800,12600,14400):
            raise ValueError('invalid exercise')
        eid = uuid.uuid4().hex
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM exercises WHERE state IN ('DISARMED','RUNNING','PAUSED')").fetchone():
                raise ValueError('stop existing exercise before creating another')
            c.execute('INSERT INTO exercises VALUES(?,?,?,?,?,?)',
                      (eid, scoring_event_id, 'DISARMED', 0, None, duration_s))
        return eid

    def status(self, eid):
        with self.transaction() as c:
            row = c.execute('SELECT * FROM exercises WHERE id=?', (eid,)).fetchone()
            if row is None:
                raise ValueError('unknown exercise')
            return dict(row)

    def record(self, exercise_id, event_id, outcome, details=None):
        # Deliberately do not serialize arbitrary details (could include secrets).
        with self.transaction() as c:
            self.audit(c, exercise_id, event_id, outcome)

    @staticmethod
    def audit(c, eid, event, outcome):
        c.execute('INSERT INTO audit(exercise,event,outcome) VALUES(?,?,?)', (eid, event, outcome))
        c.execute('DELETE FROM audit WHERE id <= (SELECT MAX(id)-100000 FROM audit)')

    def ack(self, eid, event, guest, outcome):
        if outcome not in ('APPLIED', 'FAILED', 'REJECTED'):
            raise ValueError('invalid outcome')
        with self.transaction() as c:
            r = c.execute('UPDATE dispatch SET outcome=? WHERE exercise=? AND event=? AND guest=? AND outcome=?',
                          (outcome, eid, event, guest, 'ACCEPTED'))
            if r.rowcount != 1:
                raise ValueError('unknown or already acknowledged event')
            self.audit(c, eid, event, outcome)

    def accept(self, eid, event, guest, scoring, now):
        with self.transaction() as c:
            row = c.execute('SELECT * FROM exercises WHERE id=?', (eid,)).fetchone()
            if (row is None or row['state'] != 'RUNNING' or scoring is None
                    or scoring != {'id': row['scoring_event_id'], 'state': 'RUNNING'}):
                raise ValueError('exercise not running')
            r = c.execute("UPDATE dispatch SET outcome='ACCEPTED' WHERE exercise=? AND event=? AND guest=? "
                          "AND outcome='DISPATCHED' AND expires>?", (eid, event, guest, now))
            if r.rowcount != 1:
                raise ValueError('event not acceptable')
            self.audit(c, eid, event, 'ACCEPTED')
