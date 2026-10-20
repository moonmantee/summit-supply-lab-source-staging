import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import sys

base = Path('/home/jwang/summit-scoring')
sys.path.insert(0, str(base))
import scorer
certificate = Path('/home/jwang/network-migration/shop01-migrated.crt')
config_path = base / 'config.json'
original = json.loads(config_path.read_text())
proposed = dict(original, url='https://10.77.30.10/', ca_file=str(certificate))
status, reason = scorer.check(proposed)
if status != 'PASS':
    raise SystemExit(f'New service check failed: {status}: {reason}')
backup = base / 'backups' / ('network-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(parents=True, mode=0o700)
with sqlite3.connect(base / 'state/results.sqlite3') as db:
    count = db.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]
    with sqlite3.connect(backup / 'results.sqlite3') as destination:
        db.backup(destination)
for name in ['config.json', 'summit-shop01.crt']:
    shutil.copy2(base / name, backup / name)
shutil.copy2(certificate, base / 'summit-shop01.crt')
proposed['ca_file'] = str(base / 'summit-shop01.crt')
temporary = base / 'config.json.new'
temporary.write_text(json.dumps(proposed, indent=2) + '\n')
temporary.replace(config_path)
assert scorer.check(proposed)[0] == 'PASS'
wrong = dict(proposed, expected=['SUMMIT-TEST-ABSENT-MARKER'])
assert scorer.check(wrong)[0] == 'FAIL'
print(f'HTTPS PASS; wrong content FAIL; all {count} historical records preserved. Backup: {backup}')
