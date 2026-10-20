"""Explicit local preview with fictional scoring data; never used on score01."""
from contextlib import closing
import argparse
import datetime as dt
from pathlib import Path
import shutil
import sqlite3
import time
import tempfile
import scorer
from lifecycle import migrate_lifecycle, transition_event
from portal_store import PortalStore
from portal_server import write_auth,make_server

parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,default=8877)
parser.add_argument('--fresh',action='store_true')
args=parser.parse_args()
tmp=Path(__file__).resolve().parent.parent/'.tmp'
tmp.mkdir(exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='team-portal-preview-',dir=tmp)) if args.fresh else tmp/'team-portal-preview'
root.mkdir(parents=True,exist_ok=True)
score=root/'scoring.db'
with closing(sqlite3.connect(score)) as db:
    scorer.initialize_schema(db)
    migrate_lifecycle(db,dt.datetime.now(dt.timezone.utc).isoformat())
    transition_event(db,'start',dt.datetime.now(dt.timezone.utc).isoformat())
stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
with closing(sqlite3.connect(score)) as db,db:
    db.execute('DELETE FROM service_checks'); db.execute('DELETE FROM event_service_state')
    for i,(host,name,status) in enumerate([('dc01','DNS','PASS'),('dc01','SSH','PASS'),('workstation01','SSH','PASS'),('shop01','HTTPS storefront','PASS'),('shop01','SSH','PASS'),('sql01','SSH','PASS'),('forum01','HTTP forum','PASS'),('forum01','FTP','PASS'),('forum01','SSH','PASS'),('mail01','SMTP','PASS'),('mail01','IMAPS','DOWN'),('mail01','HTTPS webmail','PASS'),('mail01','SSH','PASS')],1):
        ident=host+'-'+str(i); total=80 if status=='PASS' else 0
        db.execute('INSERT INTO event_service_state VALUES(1,?,?,?,?,?,?)',(ident,0,total,0,status,stamp))
        db.execute('INSERT INTO service_checks(id,event_id,round_id,timestamp,service_id,host_name,service_name,status,reason,latency_ms,awarded_points,sla_deduction,consecutive_failures) VALUES(?,1,1,?,?,?,?,?,?,?,?,?,?)',(i,stamp,ident,host,name,status,'preview',14,total,0,0))
store=PortalStore(root/'portal.db',score)
write_auth(root/'auth.json','preview-team-password','preview-admin-password')
files=root/'files';files.mkdir(exist_ok=True)
shared=Path(__file__).resolve().parent.parent
shutil.copy2(shared/'COMPETITION-README.md',files/'README.md')
shutil.copy2(shared/'COMPETITION-README.docx',files/'README.docx')
store.settings({'team_name':'Summit Blue Team','help_contact':'White Team desk · room 204','credential_contact':'Request a credential update at the White Team desk.'})
if not store.snapshot()['announcements']: store.announce('LOCAL PREVIEW — Service results on this page are fictional fixtures. Live score01 deployment is separate.')
if not store.snapshot(admin=True)['injects']:
    a=store.create({'code':'I01','title':'Publish the orders DNS record','hosts':'dc01, shop01','description':'Create orders.corp.summit.test pointing to 10.77.30.10. Preserve existing directory and DNS services.','acceptance':'White Team verifies the exact A record over UDP and TCP and checks LDAP discovery.','points':10,'deadline':time.time()+86400})
    store.release(a)
    store.create({'code':'I02','title':'PRIVATE UNRELEASED CARD','hosts':'forum01','description':'Hidden fixture','acceptance':'Hidden acceptance','points':10})
print(f'Local fixture preview on http://127.0.0.1:{args.port}/portal/ (not production)',flush=True)
make_server(store,root/'auth.json',files,port=args.port).serve_forever()
