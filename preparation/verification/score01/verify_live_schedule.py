"""Check armed live metadata and simulate the schedule only on database copies."""
from contextlib import closing
import datetime as dt
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
sys.path.insert(0,'/home/jwang/summit-portal')
from portal_store import PortalStore
from inject_services import active_services
portal=Path('/home/jwang/summit-portal/portal-state/portal.sqlite3')
score=Path('/home/jwang/summit-scoring/state/results.sqlite3')
store=PortalStore(portal,score,Path('/home/jwang/summit-scoring/config.json'))
live=store.snapshot(admin=True)
assert live['event']['state']=='STOPPED' and live['settings']['schedule_armed_at']
assert live['settings']['schedule_anchor']=='' and live['settings']['schedule_duration']=='14400'
assert [c['release_offset'] for c in live['injects']]==[0,1800,3600,5400,7200,9000]
assert all(c['grace_seconds']==1800 and c['released_at'] is None for c in live['injects'])
with tempfile.TemporaryDirectory(prefix='schedule-copy-check-') as folder:
    root=Path(folder)
    for source,name in [(portal,'portal.db'),(score,'score.db')]:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as origin,closing(sqlite3.connect(root/name)) as target: origin.backup(target)
    start=int(time.time())+1
    with closing(sqlite3.connect(root/'score.db')) as db,db:
        db.execute('UPDATE competition_events SET state=?,last_resumed_at=? WHERE id=?',('RUNNING',dt.datetime.fromtimestamp(start,dt.timezone.utc).isoformat(),live['event']['id']))
    duplicate=PortalStore(root/'portal.db',root/'score.db')
    for index in range(6):
        now=start+index*1800
        duplicate.snapshot(now=now)
        with duplicate.db() as db:
            card=dict(db.execute('SELECT * FROM injects WHERE code=? AND event_id=?',(f'I{index+1:02}',live['event']['id'])).fetchone())
        if index==2:
            assert card['released_at'] is None  # Unconfigured mail is never published.
            continue
        assert card['released_at']==now
        ident='inject-'+str(card['id'])
        assert ident not in {s['id'] for s in active_services(root/'portal.db',live['event']['id'],now=now+1799)}
        assert ident in {s['id'] for s in active_services(root/'portal.db',live['event']['id'],now=now+1800)}
print('PASS: live schedule armed for next Start; offsets 0/30/60/90/120/150 minutes; grace 30 minutes each; copy simulation excludes all task probes until grace ends; unconfigured mail stays private; no live Start or probes performed.')
