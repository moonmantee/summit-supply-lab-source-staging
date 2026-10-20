"""Validate staged code against a private COPY of score01 history; no live writes."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

package=Path('/home/jwang/team-portal-package'); score=Path('/home/jwang/summit-scoring')
sys.path.insert(0,str(score)); sys.path.insert(0,str(package))
for name,digest in json.loads((package/'SHA256SUMS.json').read_text()).items():
    assert hashlib.sha256((package/name).read_bytes()).hexdigest()==digest,name
import scorer,portal_store,portal_scoreboard
with closing(sqlite3.connect((score/'state/results.sqlite3').as_uri()+'?mode=ro',uri=True)) as live:
    live.execute('PRAGMA query_only=ON')
    before=(live.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0],live.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0])
    state=live.execute('SELECT e.id,e.state FROM competition_events e JOIN scorer_settings s ON s.current_event_id=e.id WHERE s.id=1').fetchone()
    assert state[1]=='STOPPED','Verify installation timing before proceeding: event is no longer stopped.'
    with tempfile.TemporaryDirectory(prefix='summit-portal-stage-check-') as folder:
        root=Path(folder); database=root/'results.sqlite3'
        with closing(sqlite3.connect(database)) as duplicate: live.backup(duplicate)
        config=root/'config.json'; config.write_text((score/'config.json').read_text())
        portal=portal_store.PortalStore(root/'portal.sqlite3',database,config)
        for card in json.loads((package/'portal-injects.json').read_text()): portal.create(card)
        assert portal.snapshot()['injects']==[]
        assert len(portal.snapshot(admin=True)['injects'])==6
        html=portal_scoreboard.page(portal).decode()
        assert 'Competition 1' in html and 'control-panel' not in html and 'summit-control-token' not in html
        result=scorer.run_scoring_round(config,database,root/'public')
        assert not result['recorded']
        with closing(sqlite3.connect(database)) as duplicate:
            assert duplicate.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0]==before[0]
            assert duplicate.execute('SELECT COUNT(*) FROM service_checks').fetchone()[0]==before[1]
    print(json.dumps({'stage_verified':True,'event_id':state[0],'event_state':state[1],'existing_rounds':before[0],'existing_service_checks':before[1],'drafts':6,'live_database_writes':False}))
