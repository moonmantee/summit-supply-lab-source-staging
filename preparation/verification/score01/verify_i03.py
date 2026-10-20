"""Read-only live verification; no scoring round and no secret output."""
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
portal=Path('/home/jwang/summit-portal'); score=Path('/home/jwang/summit-scoring')
sys.path.insert(0,str(portal))
from portal_store import PortalStore
from inject_services import validate, active_services
store=PortalStore(portal/'portal-state/portal.sqlite3',score/'state/results.sqlite3',score/'config.json')
event=store.event()
with store.db() as db:
    card=dict(db.execute("SELECT * FROM injects WHERE event_id=? AND code='I03'",(event['id'],)).fetchone())
    template=json.loads(db.execute("SELECT value FROM settings WHERE key='inject_template'").fetchone()[0])
    future=next(c for c in template['cards'] if c['code']=='I03')
    attachments=[dict(a) for a in db.execute('SELECT name,stored_name FROM attachments WHERE inject_id=?',(card['id'],))]
service=validate(json.loads(card['service_json']))
assert json.loads(future['service_json'])==service
assert future['grace_seconds']==card['grace_seconds']==1800
assert future['release_offset']==card['release_offset']==3600
assert len(attachments)==2
for attachment in attachments:
    path=portal/'portal-state/files/attachments'/attachment['stored_name']
    assert path.is_file() and path.stat().st_mode & 0o777==0o600
cert=ssl._ssl._test_decode_cert(service['ca_file'])
assert ('DNS',service['server_name']) in cert['subjectAltName']
assert ssl.cert_time_to_seconds(cert['notAfter'])>time.time()
for unit in ['summit-team-portal.service','summit-check.timer','summit-scoreboard.service']:
    subprocess.run(['systemctl','--user','is-active','--quiet',unit],check=True)
assert not (Path('/home/jwang/i03-config-stage')/'mail-input.json').exists()
unreleased_or_grace=card['released_at'] is None or time.time()<card['released_at']+1800
if unreleased_or_grace: assert not any(s['id']==f'inject-{card["id"]}' for s in active_services(store.path,event['id']))
ports={}
for port in [587,993]:
    try:
        with socket.create_connection(('10.77.30.30',port),timeout=3): ports[port]='reachable'
    except OSError: ports[port]='not reachable (competitor setup required)'
release=dt.datetime.fromtimestamp(card['release_at'],dt.timezone.utc).isoformat() if card['release_at'] else None
print(json.dumps({'verified':True,'event':event,'I03_release_utc':release,'released':card['released_at'] is not None,'inactive_until_grace':unreleased_or_grace,'points':service['points'],'sla_penalty':service['sla_penalty'],'completion_points':card['points'],'attachments':[a['name'] for a in attachments],'certificate_identity_and_validity':True,'mail_ports':ports,'services_active':True,'private_staging_removed':True}))
