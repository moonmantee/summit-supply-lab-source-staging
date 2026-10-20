"""Install the tested UI while preserving existing scoring records."""
import datetime
import shutil
import sqlite3
from pathlib import Path

base = Path(__file__).resolve().parent
candidate = base / 'ui-candidate'
backup = base / 'backups' / datetime.datetime.now(datetime.timezone.utc).strftime('ui-%Y%m%dT%H%M%SZ')
backup.mkdir(parents=True, mode=0o700)
with sqlite3.connect(base / 'state/results.sqlite3') as db:
    with sqlite3.connect(backup / 'results.sqlite3') as destination:
        db.backup(destination)
for name in ['scorer.py', 'reporting.py', 'scoreboard.css', 'scoreboard.js']:
    if (base / name).exists():
        shutil.copy2(base / name, backup / name)
shutil.copytree(base / 'public', backup / 'public')
for name in ['reporting.py', 'scoreboard.css', 'scoreboard.js', 'scorer.py', 'test_reporting.py']:
    temporary = base / (name + '.new')
    shutil.copy2(candidate / name, temporary)
    temporary.replace(base / name)
import scorer
with sqlite3.connect(base / 'state/results.sqlite3') as db:
    scorer.render_report(db, base / 'public')
    count = db.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]
assert (base / 'public/history.html').read_text().count('data-check=') == count
print(f'Updated scoreboard; {count} existing checks preserved. Backup: {backup}')
