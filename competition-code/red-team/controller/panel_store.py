"""Coordinator-owned revisions and immutable exercise snapshots."""
import json
import shutil
import time
import uuid
from panel_catalog import PanelError


def encode(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':'))


class PanelStore:
    def __init__(self, store, clock=time.time, free_bytes=None):
        self.store, self.clock = store, clock
        self.free_bytes = free_bytes or (lambda: shutil.disk_usage(store.path.parent).free)

    def initialize(self, current_scenario, imports):
        statements = [
            'CREATE TABLE IF NOT EXISTS panel_meta(id INTEGER PRIMARY KEY CHECK(id=1), lifecycle_revision INTEGER NOT NULL)',
            'INSERT OR IGNORE INTO panel_meta VALUES(1,0)',
            'CREATE TABLE IF NOT EXISTS panel_profiles(id TEXT PRIMARY KEY,name TEXT,head INTEGER,pinned INTEGER)',
            'CREATE TABLE IF NOT EXISTS panel_revisions(profile TEXT,revision INTEGER,document TEXT,created REAL,PRIMARY KEY(profile,revision))',
            'CREATE TABLE IF NOT EXISTS panel_snapshots(exercise TEXT PRIMARY KEY,profile TEXT,revision INTEGER,document TEXT)',
            'CREATE TABLE IF NOT EXISTS panel_admin_audit(id INTEGER PRIMARY KEY,created REAL,actor TEXT,op TEXT,exercise TEXT)',
            'CREATE TABLE IF NOT EXISTS panel_idempotency(key TEXT PRIMARY KEY,body TEXT,result TEXT,created REAL)',
            '''CREATE TRIGGER IF NOT EXISTS panel_lifecycle_update AFTER UPDATE OF state ON exercises
               WHEN OLD.state != NEW.state BEGIN UPDATE panel_meta SET lifecycle_revision=lifecycle_revision+1 WHERE id=1; END''',
            '''CREATE TRIGGER IF NOT EXISTS panel_lifecycle_insert AFTER INSERT ON exercises
               BEGIN UPDATE panel_meta SET lifecycle_revision=lifecycle_revision+1 WHERE id=1; END''',
        ]
        with self.store.transaction() as tx:
            for statement in statements: tx.execute(statement)
            for profile_id, document in imports.items():
                if not tx.execute('SELECT 1 FROM panel_profiles WHERE id=?', (profile_id,)).fetchone():
                    self.write_profile(tx, None, None, document, imported_id=profile_id)
            row = tx.execute('SELECT * FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
            if current_scenario is not None and row and not tx.execute('SELECT 1 FROM panel_snapshots WHERE exercise=?', (row['id'],)).fetchone():
                tx.execute('INSERT INTO panel_snapshots VALUES(?,?,?,?)',
                           (row['id'], None, None, encode(dict(name='Imported current schedule', duration=int(row['duration']), events=current_scenario))))

    def check_space(self):
        if self.free_bytes() < 256 * 1024 * 1024:
            raise PanelError('low_disk', 'At least 256 MiB free space is required')

    def list_profiles(self):
        with self.store.transaction() as tx:
            result = []
            for p in tx.execute('SELECT * FROM panel_profiles ORDER BY name,id'):
                body = json.loads(tx.execute('SELECT document FROM panel_revisions WHERE profile=? AND revision=?', (p['id'], p['head'])).fetchone()[0])
                result.append(dict(id=p['id'], name=p['name'], revision=p['head'], pinned_revision=p['pinned'],
                                   event_count=len(body['events']), duration=body['duration']))
            return result

    def read_profile(self, profile_id, revision=None, tx=None):
        if tx is None:
            with self.store.transaction() as connection: return self.read_profile(profile_id, revision, connection)
        profile = tx.execute('SELECT * FROM panel_profiles WHERE id=?', (profile_id,)).fetchone()
        if not profile: raise PanelError('invalid', 'Unknown profile')
        revision = profile['head'] if revision is None else revision
        if type(revision) is not int: raise PanelError('invalid', 'Invalid profile revision')
        row = tx.execute('SELECT * FROM panel_revisions WHERE profile=? AND revision=?', (profile_id, revision)).fetchone()
        if not row: raise PanelError('invalid', 'Revision is unavailable')
        return dict(id=profile_id, revision=revision, head_revision=profile['head'],
                    revisions=[r[0] for r in tx.execute('SELECT revision FROM panel_revisions WHERE profile=? ORDER BY revision DESC', (profile_id,))],
                    document=json.loads(row['document']))

    def write_profile(self, tx, profile_id, expected_revision, document, imported_id=None):
        self.check_space()
        if profile_id is None:
            if tx.execute('SELECT count(*) FROM panel_profiles').fetchone()[0] >= 64:
                raise PanelError('limit', 'At most 64 profiles are allowed')
            profile_id, revision = imported_id or uuid.uuid4().hex, 1
            tx.execute('INSERT INTO panel_profiles VALUES(?,?,?,?)', (profile_id, document['name'], 1, 1 if imported_id else None))
        else:
            old = self.read_profile(profile_id, None, tx)
            if type(expected_revision) is not int or old['revision'] != expected_revision:
                raise PanelError('conflict', 'Profile changed; review the latest revision')
            revision = old['revision'] + 1
            tx.execute('UPDATE panel_profiles SET name=?,head=? WHERE id=?', (document['name'], revision, profile_id))
        tx.execute('INSERT INTO panel_revisions VALUES(?,?,?,?)', (profile_id, revision, encode(document), self.clock()))
        pinned = tx.execute('SELECT pinned FROM panel_profiles WHERE id=?', (profile_id,)).fetchone()[0]
        keep = [r[0] for r in tx.execute('SELECT revision FROM panel_revisions WHERE profile=? AND revision != ? ORDER BY revision DESC LIMIT ?',
                                       (profile_id, pinned or -1, 19 if pinned else 20))]
        if pinned: keep.append(pinned)
        tx.execute('DELETE FROM panel_revisions WHERE profile=? AND revision NOT IN (%s)' % ','.join('?' for _ in keep), (profile_id, *keep))
        return self.read_profile(profile_id, revision, tx)

    def load_snapshot(self, tx, profile_id, revision, scoring_event_id):
        self.check_space()
        profile = self.read_profile(profile_id, revision, tx)
        if type(scoring_event_id) is not int or scoring_event_id < 1: raise PanelError('invalid', 'Invalid scoring event')
        current = tx.execute('SELECT * FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
        if current and current['state'] in ('RUNNING', 'PAUSED'): raise PanelError('conflict', 'Stop the current exercise before loading')
        if current:
            tx.execute("UPDATE dispatch SET outcome='REVOKED' WHERE exercise=? AND outcome='DISPATCHED'", (current['id'],))
            if current['state'] == 'DISARMED': tx.execute("UPDATE exercises SET state='STOPPED',last_tick=NULL WHERE id=?", (current['id'],))
        eid = uuid.uuid4().hex
        tx.execute('INSERT INTO exercises VALUES(?,?,?,?,?,?)', (eid, scoring_event_id, 'DISARMED', 0, None, profile['document']['duration']))
        tx.execute('INSERT INTO panel_snapshots VALUES(?,?,?,?)', (eid, profile_id, revision, encode(profile['document'])))
        return dict(exercise_id=eid, profile_id=profile_id, revision=revision, document=profile['document'])

    def read_snapshot(self, exercise_id):
        with self.store.transaction() as tx:
            row = tx.execute('SELECT * FROM panel_snapshots WHERE exercise=?', (exercise_id,)).fetchone()
            return None if row is None else dict(exercise_id=exercise_id, profile_id=row['profile'], revision=row['revision'], document=json.loads(row['document']))
