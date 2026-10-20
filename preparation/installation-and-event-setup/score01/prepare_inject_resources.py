"""Generate dedicated fictional task resources on score01; never alter guests."""
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import zipfile
from portal_store import PortalStore

BASE=Path(__file__).resolve().parent
root=BASE/'portal-state'; resources=root/'resources'; resources.mkdir(mode=0o700,exist_ok=True)
files=root/'files/attachments'; files.mkdir(mode=0o700,parents=True,exist_ok=True)
score=Path('/home/jwang/summit-scoring')
store=PortalStore(root/'portal.sqlite3',score/'state/results.sqlite3',score/'config.json')
event=store.event()
fixture=resources/'inventory.csv'
if not fixture.exists(): fixture.write_text('sku,item,quantity\nSUM-100,Shipping boxes,120\nSUM-200,Packing tape,80\nSUM-300,Barcode labels,250\n',encoding='utf-8')
account=resources/'ftp-account.json'
if not account.exists(): account.write_text(json.dumps({'username':'inventory_reader','password':secrets.token_urlsafe(20)}),encoding='utf-8')
credentials=json.loads(account.read_text())
shipping=(BASE/'inject-resources/shipping-policy.txt').read_bytes()
health=(BASE/'inject-resources/health.json').read_bytes()
tls=resources/'forum-tls'; tls.mkdir(mode=0o700,exist_ok=True)
if not (tls/'forum.crt').exists():
    subprocess.run(['openssl','req','-x509','-newkey','rsa:3072','-nodes','-sha256','-days','365','-keyout',str(tls/'forum.key'),'-out',str(tls/'forum.crt'),'-subj','/CN=forum01.corp.summit.test','-addext','subjectAltName=DNS:forum01.corp.summit.test','-addext','basicConstraints=critical,CA:TRUE'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
bundle=resources/'forum-https-package.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
    archive.write(tls/'forum.key','forum.key'); archive.write(tls/'forum.crt','forum.crt')
    archive.writestr('INSTALL.txt','Install this lab-only PEM certificate and key on forum01 port 443. Bind forum01.corp.summit.test. Keep the key restricted to the service account. Redirect HTTP / to https://forum01.corp.summit.test/. Preserve the existing forum. The scorer trusts this certificate and verifies its DNS name. No public certificate authority is needed.\n')
definitions={
 'I01':{'probe':'dns_record','host':'10.77.40.10','name':'orders.corp.summit.test','answer':'10.77.30.10','points':2,'sla_penalty':7},
 'I02':{'probe':'ftp_share','host':'10.77.30.20',**credentials,'file':'inventory.csv','sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'points':2,'sla_penalty':7},
 'I04':{'probe':'https_upgrade','host':'10.77.30.20','server_name':'forum01.corp.summit.test','ca_file':str(tls/'forum.crt'),'path':'/','expected':['Summit'],'points':5,'sla_penalty':15},
 'I05':{'probe':'http_resource','host':'10.77.30.10','scheme':'https','port':443,'path':'/shipping-policy.txt','ca_file':str(score/'summit-shop01.crt'),'sha256':hashlib.sha256(shipping).hexdigest(),'points':3,'sla_penalty':10},
 'I06':{'probe':'http_resource','host':'10.77.20.10','scheme':'http','port':8080,'path':'/health.json','sha256':hashlib.sha256(health).hexdigest(),'points':3,'sla_penalty':10},
}
for card in store.snapshot(admin=True)['injects']:
    if card['code'] in definitions and card['released_at'] is None:
        if card['needs_configuration']: store.configure_service(card['id'],definitions[card['code']],expected_event_id=event['id'])
        attachments=[]
        if card['code']=='I02':
            attachments=[('inventory.csv',fixture.read_bytes()),('FTP-ACCOUNT.txt',f'Create a NEW account for the inventory share.\nUsername: {credentials["username"]}\nPassword: {credentials["password"]}\nFile: inventory.csv\nPassive FTP on forum01:21. Allow retrieval and deny all writes and anonymous inventory access. Preserve ftp_reader.\n'.encode())]
        if card['code']=='I04': attachments=[('forum-https-package.zip',bundle.read_bytes())]
        if card['code']=='I05': attachments=[('shipping-policy.txt',shipping)]
        if card['code']=='I06': attachments=[('health.json',health)]
        with store.db() as db:
            for name,data in attachments:
                if db.execute('SELECT 1 FROM attachments WHERE inject_id=? AND name=?',(card['id'],name)).fetchone(): continue
                stored=secrets.token_hex(20); path=files/stored; path.write_bytes(data); path.chmod(0o600)
                db.execute('INSERT INTO attachments(inject_id,name,stored_name) VALUES(?,?,?)',(card['id'],name,stored))
for path in resources.rglob('*'):
    path.chmod(0o700 if path.is_dir() else 0o600)
print('Private DNS, FTP, HTTPS, shipping-policy and warehouse task checks/resources prepared. Mail task requires organizer mailbox/TLS configuration before release. No tasks released; no guest changed.')
