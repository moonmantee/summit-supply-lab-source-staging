"""Read-only verification of the deployed event-aware scorer."""
import json
import os
from pathlib import Path
import sqlite3
import urllib.request

import scorer
from lifecycle import get_current_event, list_events


base = Path(__file__).resolve().parent
config = json.loads((base / 'config.json').read_text(encoding='utf-8'))
services = scorer.resolve_services(config)
assert len(services) == 13
assert sum(service['points'] for service in services) == 34

with sqlite3.connect(base / 'state' / 'results.sqlite3') as db:
    current = get_current_event(db)
    events = list_events(db)
    practice = [event for event in events if event.kind == 'practice-import']
    assert current.name == 'Competition 1', current
    assert current.state == 'READY', current
    assert len(practice) == 1 and practice[0].state == 'ARCHIVED', practice
    current_rounds = db.execute(
        'SELECT COUNT(*) FROM scoring_rounds WHERE event_id=?', (current.id,)
    ).fetchone()[0]
    current_checks = db.execute(
        'SELECT COUNT(*) FROM service_checks WHERE event_id=?', (current.id,)
    ).fetchone()[0]
    current_state = db.execute(
        'SELECT COUNT(*) FROM event_service_state WHERE event_id=?', (current.id,)
    ).fetchone()[0]
    assert (current_rounds, current_checks, current_state) == (0, 0, 0)
    practice_rounds = db.execute(
        'SELECT COUNT(*) FROM scoring_rounds WHERE event_id=?', (practice[0].id,)
    ).fetchone()[0]
    practice_checks = db.execute(
        'SELECT COUNT(*) FROM service_checks WHERE event_id=?', (practice[0].id,)
    ).fetchone()[0]
    assert practice_rounds > 0 and practice_checks > 0
    legacy = db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='rounds'"
    ).fetchone()[0]
    legacy_rows = db.execute('SELECT COUNT(*) FROM rounds').fetchone()[0] if legacy else 0
    print('Events:', [(event.id, event.name, event.state) for event in events])
    print('Archived practice rounds/checks:', practice_rounds, practice_checks)
    print('Preserved legacy checks:', legacy_rows)

token_path = base / 'state' / 'control-token'
assert token_path.is_file()
assert os.stat(token_path).st_mode & 0o777 == 0o600
assert len(token_path.read_text(encoding='ascii').strip()) >= 32

index = (base / 'public' / 'index.html').read_text(encoding='utf-8')
history = (base / 'public' / 'history.html').read_text(encoding='utf-8')
assert 'data-event-state="READY"' in index
assert 'id="start-control"' in index
assert 'id="stop-control" disabled' in index
assert 'history-grid' in history
assert (base / 'public' / f'history-event-{practice[0].id}.html').is_file()

with urllib.request.urlopen('http://127.0.0.1:8766/', timeout=5) as response:
    page = response.read().decode('utf-8')
    assert response.status == 200
    assert 'Competition 1' in page and 'READY' in page

print('READY lifecycle, archived practice history, controls, grid, token, and local server verified')
