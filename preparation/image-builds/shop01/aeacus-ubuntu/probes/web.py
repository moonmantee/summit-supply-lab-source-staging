"""Bounded HTTPS behavior checks for synthetic fixtures and actual logging."""
import http.client
import re
import ssl
import time
import uuid
from pathlib import Path
from common import ProbeError, active, read, run

ISSUES=tuple(range(30,38))
FIXTURES=Path('/var/www/summit/training-fixtures')
URLS={30:'/training-fixtures/listing/',31:'/server-status?auto',32:'/training-fixtures/public-backup.sql',
      33:'/training-fixtures/.private-note',34:'/training-fixtures/cgi/marker.cgi',35:'/training-fixtures/ssi/marker.shtml'}
PATHS={30:FIXTURES/'listing',32:FIXTURES/'public-backup.sql',33:FIXTURES/'.private-note',
       34:FIXTURES/'cgi/marker.cgi',35:FIXTURES/'ssi/marker.shtml'}
MARKERS=('SUM-101','SUM-102','SUM-103','Ridgeline daypack','Alpine insulated bottle','Trail first aid kit')

def healthy_catalog(body):
    return all(m in body for m in MARKERS) and 'order.php' in body

def evaluate(issue,d):
    if d.get('running') is not True or d.get('home_ok') is not True: return False
    if issue in (36,37):
        return all(d.get(k) is True for k in ('configured','file_exists','delivery_evidence'))
    if d.get('fixture_ready') is not True: return False
    if issue in (30,34,35) and d.get('fixture_retained') is not True: return False
    status=d.get('status'); body=d.get('body','')
    if issue in (30,31,32,33): return status in (403,404)
    if issue==34: return status in (403,404) or (status==200 and 'SUMMIT-CGI-EXECUTED' not in body and 'Content-Type:' not in body)
    if issue==35: return status in (403,404) or (status==200 and 'SUMMIT-SSI-EXECUTED' not in body)
    return False

def fetch(path):
    try:
        context=ssl.create_default_context(cafile='/etc/ssl/certs/summit-shop01.crt')
        connection=http.client.HTTPSConnection('10.77.30.10',timeout=6,context=context)
        try:
            connection.request('GET',path,headers={'Host':'shop01.corp.summit.test'})
            response=connection.getresponse(); body=response.read(262145)
            if len(body)>262144: raise ProbeError('Oversized web response')
            return response.status,body.decode('utf-8',errors='replace')
        finally: connection.close()
    except (OSError,http.client.HTTPException) as e:
        raise ProbeError(type(e).__name__) from None

def tail(path):
    p=Path(path)
    if not p.is_file(): return ''
    with p.open('rb') as f:
        f.seek(max(0,p.stat().st_size-32768)); return f.read().decode('utf-8',errors='replace')

def wait_for_token(path,token,timeout=1.0):
    deadline=time.monotonic()+timeout
    while True:
        if token in tail(path): return True
        remaining=deadline-time.monotonic()
        if remaining<=0: return False
        time.sleep(min(0.02,remaining))

def apache_open_log(path):
    for pid in run(['pidof','apache2']).split():
        for descriptor in (Path('/proc')/pid/'fd').iterdir():
            try:
                if str(descriptor.readlink())==str(path): return True
            except FileNotFoundError: continue
    return False

def collect(issue):
    if not active('apache2'): return {'running':False}
    token=uuid.uuid4().hex
    status,body=fetch('/?summit-log-probe='+token)
    d={'running':True,'home_ok':status==200 and healthy_catalog(body)}
    if issue in (30,31,32,33,34,35):
        # .ready is organizer fixture provenance, not a score toggle; require
        # actual behavior and retained execution/listing objects independently.
        d['fixture_ready']=(FIXTURES/'.ready').is_file()
        d['status'],d['body']=fetch(URLS[issue])
        d['fixture_retained']=issue not in PATHS or PATHS[issue].exists()
        return d
    if issue in (36,37):
        site=Path('/etc/apache2/sites-enabled/summit-shop.conf')
        text=read(site)
        lines='\n'.join(l.split('#',1)[0].strip() for l in text.splitlines())
        directive='CustomLog' if issue==36 else 'ErrorLog'
        name='summit-access.log' if issue==36 else 'summit-error.log'
        path=Path('/var/log/apache2')/name
        configured=bool(re.search(r'(?m)^'+directive+r'\s+(?:\$\{APACHE_LOG_DIR\}|/var/log/apache2)/'+re.escape(name)+r'(?:\s|$)',lines))
        d.update(configured=configured,file_exists=path.is_file())
        if issue==36: d['delivery_evidence']=wait_for_token(path,token)
        else:
            status,_=fetch('/training-fixtures/SUMMIT-ERROR-VALIDATION/'+token+'.txt')
            d['delivery_evidence']=status==403 and apache_open_log(path) and wait_for_token(path,token)
        return d
    raise ProbeError('Unsupported web objective')

def check(issue): return evaluate(issue,collect(issue))
