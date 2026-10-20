"""Configure the existing mail inject without solving it or changing the event clock."""
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
import ssl
import base64
import subprocess
import sys
import time

portal=Path('/home/jwang/summit-portal'); score=Path('/home/jwang/summit-scoring'); stage=Path('/home/jwang/i03-config-stage')
def active(unit): return subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode==0
def ctl(*args): subprocess.run(['systemctl','--user',*args],check=True)
timer=active('summit-check.timer'); running=active('summit-team-portal.service')
backup=Path('/home/jwang/portal-upgrade-backups')/('i03-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')); backup.mkdir(mode=0o700,parents=True)
saved=[]; db_ready=False; created=[]; trust_saved=False
trust=portal/'portal-state/resources/mail-webmail.crt'
try:
    private=json.loads((stage/'mail-input.json').read_text())
    if private['server_name']!='webmail.corp.summit.test' or private['username']!='operations@Summit': raise ValueError('Unexpected mailbox identity')
    ctl('stop','summit-check.timer')
    until=time.monotonic()+65
    while active('summit-check.service'):
        if time.monotonic()>until: raise RuntimeError('Scoring round still active; retry later.')
        time.sleep(1)
    ctl('stop','summit-team-portal.service')
    with closing(sqlite3.connect(portal/'portal-state/portal.sqlite3')) as source,closing(sqlite3.connect(backup/'portal.sqlite3')) as target: source.backup(target)
    (backup/'portal.sqlite3').chmod(0o600); db_ready=True
    for index,target in enumerate([portal/'inject_services.py',score/'inject_services.py']):
        prior=backup/str(index); shutil.copy2(target,prior); saved.append((target,prior))
        temp=target.with_suffix('.update'); shutil.copy2(stage/'inject_services.py',temp); temp.chmod(0o600); temp.replace(target)
    sys.path.insert(0,str(portal))
    from portal_store import PortalStore
    store=PortalStore(portal/'portal-state/portal.sqlite3',score/'state/results.sqlite3',score/'config.json')
    event=store.event()
    with store.db() as db:
        card=dict(db.execute("SELECT * FROM injects WHERE event_id=? AND code='I03'",(event['id'],)).fetchone())
    if card['released_at'] is not None: raise RuntimeError('I03 already released; immutable task was not changed.')
    if trust.exists():
        shutil.copy2(trust,backup/'mail-webmail.crt'); trust_saved=True
    else: created.append(trust)
    trust.write_text(ssl.DER_cert_to_PEM_cert(base64.b64decode(private['certificate_base64'])),encoding='ascii'); trust.chmod(0o600)
    ssl.create_default_context(cafile=str(trust))
    service={'probe':'mail_alias','host':'10.77.30.30','server_name':private['server_name'],'ca_file':str(trust),'username':private['username'],'password':private['password'],'sender':private['sender'],'recipient':'dispatch@corp.summit.test','points':4,'sla_penalty':12}
    store.configure_service(card['id'],service,expected_event_id=event['id'])
    instructions=f'''I03: Dispatch alias and secure mail access
Host: mail01 (10.77.30.30), MailEnable, post office Summit
Existing mailbox login: {private['username']}
Existing mailbox password: {private['password']}
Mailbox address: {private['sender']}
Required alias: dispatch@corp.summit.test -> operations mailbox
TLS identity: webmail.corp.summit.test
Existing Windows certificate thumbprint: 9022BCC5290165636CD08B5B636B592D16314674
The attached public certificate is trusted by score01. No private key is distributed.

Configure authenticated SMTP submission on TCP 587 with STARTTLS and secure IMAP on TCP 993. Use the existing certificate in the Local Computer certificate store for both MailEnable services. Add the dispatch alias to the existing operations mailbox in the Summit post office. Retain the existing SMTP 25, IMAP 143 and webmail services.
In MailEnable Administration, select the certificate in Servers > localhost > Properties > SSL. Configure the SMTP inbound submission listener to offer STARTTLS and the IMAP alternate port 993 to require SSL. Restart only affected mail services when necessary. Allow score01 (10.77.70.10) through the Windows firewall for 587 and 993; White Team provides the range firewall path.
The scorer connects directly to mail01's IP and verifies the named TLS certificate; no new DNS record is required for this task. Do not replace the existing operations account or rotate its supplied password during this task.

Scoring: release at event start + 60 minutes; 30-minute grace after actual publication. After grace, every PASS earns 4 service uptime points; five consecutive DOWN rounds incur a 12-point SLA deduction. Three consecutive PASS rounds before the event deadline award 15 one-time completion points. The check authenticates over STARTTLS, sends a uniquely tagged message to dispatch, and finds it in operations over trusted IMAPS within eight seconds. Only tagged probe messages are marked deleted; other mail is preserved.
'''
    with store.db() as db:
        db.execute('UPDATE injects SET description=?,acceptance=? WHERE id=?',('Create dispatch@corp.summit.test as an alias for the existing operations mailbox. Enable authenticated STARTTLS submission on 587 and trusted IMAPS on 993 using mail01\'s existing certificate. Download the attached mailbox and TLS instructions. Preserve baseline mail and webmail services.', 'Authenticated STARTTLS SMTP on 587 submits a fresh tagged dispatch message; trusted IMAPS on 993 finds it in operations within eight seconds. After the 30-minute grace, each PASS earns 4 uptime points and five consecutive DOWN rounds incur a 12-point SLA deduction. Three consecutive passing rounds before the deadline award 15 completion points.',card['id']))
        for name,data in [('MAIL-TASK-INSTRUCTIONS.txt',instructions.encode()),('webmail-public.crt',trust.read_bytes())]:
            if db.execute('SELECT 1 FROM attachments WHERE inject_id=? AND name=?',(card['id'],name)).fetchone(): raise RuntimeError('Attachment already exists; inspect before retrying.')
            stored=secrets.token_hex(20); path=portal/'portal-state/files/attachments'/stored; created.append(path); path.write_bytes(data); path.chmod(0o600)
            db.execute('INSERT INTO attachments(inject_id,name,stored_name) VALUES(?,?,?)',(card['id'],name,stored))
    store.enable_event_template(event['id'])
    with store.db() as db:
        after=dict(db.execute('SELECT * FROM injects WHERE id=?',(card['id'],)).fetchone())
    for key in ['release_at','release_offset','grace_seconds','deadline','released_at','earned_points']:
        assert after[key]==card[key],key
    assert store.event()['id']==event['id'] and store.event()['state']==event['state']
    (stage/'mail-input.json').unlink()
    print(json.dumps({'configured':True,'event_id':event['id'],'event_state':event['state'],'I03_release_offset':after['release_offset'],'grace_seconds':after['grace_seconds'],'uptime_points':4,'sla_penalty':12,'completion_points':15,'attachments':2,'future_template_updated':True,'backup':str(backup)}))
except Exception:
    for target,prior in reversed(saved): shutil.copy2(prior,target)
    if db_ready: shutil.copy2(backup/'portal.sqlite3',portal/'portal-state/portal.sqlite3')
    if trust_saved: shutil.copy2(backup/'mail-webmail.crt',trust)
    for path in created: path.unlink(missing_ok=True)
    raise
finally:
    errors=[]
    for was_active,unit in [(running,'summit-team-portal.service'),(timer,'summit-check.timer')]:
        if was_active:
            try: ctl('start',unit)
            except subprocess.CalledProcessError: errors.append(unit)
    if errors: raise RuntimeError('Restart required: '+', '.join(errors))
