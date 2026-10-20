"""Competition event migration and transactional lifecycle controls."""
from dataclasses import dataclass
import sqlite3


VALID_STATES = {'READY', 'RUNNING', 'STOPPED', 'ARCHIVED'}
VALID_ACTIONS = {'start', 'stop', 'reset'}


class LifecycleError(ValueError):
    """The requested lifecycle transition is invalid."""


@dataclass(frozen=True)
class CompetitionEvent:
    id: int
    name: str
    state: str
    kind: str
    created_at: str
    started_at: str | None
    last_resumed_at: str | None
    stopped_at: str | None
    archived_at: str | None


def _columns(db, table):
    return {row[1] for row in db.execute(f'PRAGMA table_info({table})')}


def _table_exists(db, table):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _event_from_row(row):
    if row is None:
        raise LifecycleError('No current competition event is configured')
    return CompetitionEvent(*row)


def _select_event(db, event_id):
    return _event_from_row(db.execute(
        '''SELECT id,name,state,kind,created_at,started_at,last_resumed_at,stopped_at,archived_at
           FROM competition_events WHERE id=?''',
        (event_id,),
    ).fetchone())


def _next_competition_number(db):
    return db.execute(
        "SELECT COALESCE(MAX(sequence_number),0)+1 FROM competition_events WHERE kind='competition'"
    ).fetchone()[0]


def _create_competition(db, now):
    number = _next_competition_number(db)
    cursor = db.execute(
        '''INSERT INTO competition_events(name,state,kind,sequence_number,created_at)
           VALUES(?,?,?,?,?)''',
        (f'Competition {number}', 'READY', 'competition', number, now),
    )
    return cursor.lastrowid


def migrate_lifecycle(db: sqlite3.Connection, now: str) -> CompetitionEvent:
    """Idempotently add event scoping and select a fresh READY event."""
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS competition_events (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            state TEXT NOT NULL,
            kind TEXT NOT NULL,
            sequence_number INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            last_resumed_at TEXT,
            stopped_at TEXT,
            archived_at TEXT)''')
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_practice_import "
            "ON competition_events(kind) WHERE kind='practice-import'"
        )
        db.execute('''CREATE TABLE IF NOT EXISTS scorer_settings (
            id INTEGER PRIMARY KEY CHECK(id=1),
            current_event_id INTEGER NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS event_service_state (
            event_id INTEGER NOT NULL,
            service_id TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            total_points INTEGER NOT NULL DEFAULT 0,
            total_sla_deductions INTEGER NOT NULL DEFAULT 0,
            last_status TEXT,
            last_timestamp TEXT,
            PRIMARY KEY(event_id,service_id))''')

        for table in ('scoring_rounds', 'service_checks'):
            if _table_exists(db, table) and 'event_id' not in _columns(db, table):
                db.execute(f'ALTER TABLE {table} ADD COLUMN event_id INTEGER')
        if _table_exists(db, 'scoring_rounds'):
            db.execute(
                'CREATE INDEX IF NOT EXISTS scoring_rounds_event_idx '
                'ON scoring_rounds(event_id,id)'
            )
        if _table_exists(db, 'service_checks'):
            db.execute(
                'CREATE INDEX IF NOT EXISTS service_checks_event_idx '
                'ON service_checks(event_id,id)'
            )

        has_unscoped_rounds = _table_exists(db, 'scoring_rounds') and db.execute(
            'SELECT 1 FROM scoring_rounds WHERE event_id IS NULL LIMIT 1'
        ).fetchone()
        has_unscoped_checks = _table_exists(db, 'service_checks') and db.execute(
            'SELECT 1 FROM service_checks WHERE event_id IS NULL LIMIT 1'
        ).fetchone()
        has_old_state = _table_exists(db, 'service_state') and db.execute(
            'SELECT 1 FROM service_state LIMIT 1'
        ).fetchone()
        practice_id = None
        if has_unscoped_rounds or has_unscoped_checks or has_old_state:
            practice = db.execute(
                "SELECT id FROM competition_events WHERE kind='practice-import'"
            ).fetchone()
            if practice:
                practice_id = practice[0]
            else:
                practice_id = db.execute(
                    '''INSERT INTO competition_events(
                        name,state,kind,created_at,stopped_at,archived_at)
                       VALUES(?,?,?,?,?,?)''',
                    ('Pre-competition practice', 'ARCHIVED', 'practice-import', now, now, now),
                ).lastrowid
            if _table_exists(db, 'scoring_rounds'):
                db.execute(
                    'UPDATE scoring_rounds SET event_id=? WHERE event_id IS NULL',
                    (practice_id,),
                )
            if _table_exists(db, 'service_checks'):
                db.execute(
                    'UPDATE service_checks SET event_id=? WHERE event_id IS NULL',
                    (practice_id,),
                )
            if has_old_state:
                db.execute('''INSERT OR IGNORE INTO event_service_state(
                    event_id,service_id,consecutive_failures,total_points,total_sla_deductions,
                    last_status,last_timestamp)
                    SELECT ?,service_id,consecutive_failures,total_points,total_sla_deductions,
                           last_status,last_timestamp FROM service_state''',
                    (practice_id,),
                )

        setting = db.execute(
            'SELECT current_event_id FROM scorer_settings WHERE id=1'
        ).fetchone()
        if setting is None:
            event_id = _create_competition(db, now)
            db.execute(
                'INSERT INTO scorer_settings(id,current_event_id) VALUES(1,?)',
                (event_id,),
            )
        else:
            event_id = setting[0]
        event = _select_event(db, event_id)
        db.commit()
        return event
    except Exception:
        db.rollback()
        raise


def get_current_event(db: sqlite3.Connection) -> CompetitionEvent:
    row = db.execute(
        '''SELECT e.id,e.name,e.state,e.kind,e.created_at,e.started_at,
                  e.last_resumed_at,e.stopped_at,e.archived_at
           FROM scorer_settings s JOIN competition_events e ON e.id=s.current_event_id
           WHERE s.id=1'''
    ).fetchone()
    return _event_from_row(row)


def current_event_id(db: sqlite3.Connection) -> int:
    return get_current_event(db).id


def transition_event(db: sqlite3.Connection, action: str, now: str) -> CompetitionEvent:
    if action not in VALID_ACTIONS:
        raise LifecycleError('Unknown lifecycle action')
    db.execute('BEGIN IMMEDIATE')
    try:
        event = get_current_event(db)
        if action == 'start':
            if event.state not in {'READY', 'STOPPED'}:
                raise LifecycleError(f'Cannot start an event in {event.state}')
            db.execute(
                '''UPDATE competition_events
                   SET state='RUNNING',started_at=COALESCE(started_at,?),
                       last_resumed_at=?,stopped_at=NULL WHERE id=?''',
                (now, now, event.id),
            )
            result_id = event.id
        elif action == 'stop':
            if event.state != 'RUNNING':
                raise LifecycleError(f'Cannot stop an event in {event.state}')
            db.execute(
                "UPDATE competition_events SET state='STOPPED',stopped_at=? WHERE id=?",
                (now, event.id),
            )
            result_id = event.id
        else:
            db.execute(
                "UPDATE competition_events SET state='ARCHIVED',archived_at=?,stopped_at=COALESCE(stopped_at,?) WHERE id=?",
                (now, now, event.id),
            )
            result_id = _create_competition(db, now)
            db.execute(
                'UPDATE scorer_settings SET current_event_id=? WHERE id=1',
                (result_id,),
            )
        result = _select_event(db, result_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def list_events(db: sqlite3.Connection):
    return [
        _event_from_row(row)
        for row in db.execute(
            '''SELECT id,name,state,kind,created_at,started_at,last_resumed_at,stopped_at,archived_at
               FROM competition_events ORDER BY id DESC'''
        )
    ]
