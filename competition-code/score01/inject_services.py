"""Private, event-scoped service definitions and functional task probes."""
from contextlib import closing
import ftplib
import hashlib
import http.client
import imaplib
import json
from pathlib import Path
import smtplib
import socket
import sqlite3
import ssl
import struct
import time
import uuid

HOSTS={'10.77.40.10':'dc01','10.77.20.10':'workstation01','10.77.30.10':'shop01','10.77.50.20':'sql01','10.77.30.20':'forum01','10.77.30.30':'mail01'}
PROFILES={'dns_record':'New DNS record','ftp_share':'Inventory FTP share','https_upgrade':'Forum HTTPS','mail_alias':'Dispatch mail alias','http_resource':'Published web resource'}


def validate(service):
    if not isinstance(service,dict) or service.get('probe') not in PROFILES or service.get('host') not in HOSTS:
        raise ValueError('Select a supported task probe and a defended lab address.')
    required={'dns_record':['name','answer'], 'ftp_share':['username','password','file','sha256'], 'https_upgrade':['server_name','ca_file','path','expected'], 'mail_alias':['server_name','ca_file','username','password','recipient'],'http_resource':['scheme','port','path','sha256']}[service['probe']]
    for key in required:
        if not service.get(key): raise ValueError('Missing private service setting: '+key)
    if service['probe']=='dns_record' and service['answer'] not in HOSTS: raise ValueError('DNS answer must be a defended lab address.')
    if service['probe']=='http_resource':
        if service['scheme'] not in {'http','https'}: raise ValueError('Resource scheme must be HTTP or HTTPS.')
        if isinstance(service['port'],bool) or not isinstance(service['port'],int) or not 1<=service['port']<=65535: raise ValueError('Invalid resource port.')
        if not isinstance(service['path'],str) or not service['path'].startswith('/') or service['path'].startswith('//') or any(c in service['path'] for c in '\r\n'): raise ValueError('Resource path must be local to the lab endpoint.')
        digest=service['sha256']
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest): raise ValueError('Invalid resource SHA256.')
        if service['scheme']=='https' and (not isinstance(service.get('ca_file'),str) or not Path(service['ca_file']).is_absolute()): raise ValueError('HTTPS requires an absolute trusted certificate path.')
    if service['probe']=='ftp_share':
        if '/' in service['file'] or '\\' in service['file'] or service['file'] in {'.','..'}: raise ValueError('FTP fixture must be a simple filename.')
        if len(service['sha256'])!=64 or any(c not in '0123456789abcdef' for c in service['sha256']): raise ValueError('Invalid fixture SHA256.')
    if service['probe'] in {'https_upgrade','mail_alias'}:
        if not service['server_name'].endswith('.corp.summit.test'): raise ValueError('TLS name must belong to the lab domain.')
        if not Path(service['ca_file']).is_absolute(): raise ValueError('TLS CA file must be an absolute organizer path.')
    if service['probe']=='mail_alias':
        for key in ['recipient','sender']:
            value=service.get(key,service['username'])
            if not isinstance(value,str) or any(c in value for c in '\r\n') or value.count('@')!=1:
                raise ValueError('Mail addresses must be single addresses without line breaks.')
    for key,default in [('points',2),('sla_penalty',7)]:
        value=service.get(key,default)
        if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=100: raise ValueError('Service points and SLA penalties must be integers from 0 to 100.')
    return dict(service,points=service.get('points',2),sla_penalty=service.get('sla_penalty',7),timeout=5)


def active_services(path,event_id,now=None,include_grace=False):
    now=time.time() if now is None else now
    path=Path(path)
    if not path.exists(): return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        condition='' if include_grace else ' AND released_at+grace_seconds<=?'
        rows=db.execute('SELECT id,code,service_json FROM injects WHERE event_id=? AND released_at IS NOT NULL AND service_json IS NOT NULL'+condition,(event_id,) if include_grace else (event_id,now)).fetchall()
    result=[]
    for ident,code,raw in rows:
        service=validate(json.loads(raw))
        service.update(id=f'inject-{ident}',host_name=HOSTS[service['host']],service_name=code+' · '+PROFILES[service['probe']])
        result.append(service)
    return result


def _receive(sock,size):
    data=b''
    while len(data)<size:
        chunk=sock.recv(size-len(data))
        if not chunk: raise OSError('Truncated response')
        data+=chunk
    return data


def dns_record(s):
    import scorer
    probe=dict(s,probe='dns',server=s['host'],query=s['name'],expected_address=s['answer'])
    # Existing scorer validates UDP; repeat the same DNS packet over TCP.
    status,reason=scorer._dns_probe(probe)
    if status!='PASS': return status,reason
    labels=s['name'].rstrip('.').split('.')
    question=b''.join(bytes([len(x)])+x.encode('ascii') for x in labels)+b'\0'+struct.pack('!HH',1,1)
    ident=12345
    request=struct.pack('!HHHHHH',ident,0x0100,1,0,0,0)+question
    with socket.create_connection((s['host'],53),timeout=5) as sock:
        sock.sendall(struct.pack('!H',len(request))+request)
        response=_receive(sock,struct.unpack('!H',_receive(sock,2))[0])
    # Use the scorer's authoritative DNS decoder for both transports.
    if len(response)<12: return 'DOWN','TCP DNS response truncated'
    rid,flags,questions,count,_,_=struct.unpack('!HHHHHH',response[:12])
    if rid!=ident or flags&15: return 'DOWN','TCP DNS response invalid'
    offset=12; answers=[]
    for _ in range(questions): offset=scorer._skip_dns_name(response,offset)+4
    for _ in range(count):
        offset=scorer._skip_dns_name(response,offset)
        kind,cls,ttl,length=struct.unpack('!HHIH',response[offset:offset+10]); offset+=10
        data=response[offset:offset+length]; offset+=length
        if kind==1 and cls==1 and length==4: answers.append(socket.inet_ntoa(data))
    return ('PASS','DNS record verified over UDP and TCP') if answers==[s['answer']] else ('DOWN','TCP DNS answer differs')


def ftp_share(s):
    digest=hashlib.sha256(); size=0; end=time.monotonic()+12
    def collect(chunk):
        nonlocal size
        size+=len(chunk)
        if size>1024*1024 or time.monotonic()>end: raise OSError('Fixture transfer exceeds limit')
        digest.update(chunk)
    with ftplib.FTP() as ftp:
        ftp.connect(s['host'],21,timeout=5); ftp.login(s['username'],s['password']); ftp.set_pasv(True)
        ftp.retrbinary('RETR '+s['file'],collect)
        if digest.hexdigest()!=s['sha256']: return 'DOWN','Inventory fixture content differs'
        # A disposable filename tests write denial without overwriting business data.
        import io
        name='.score01-write-test-'+uuid.uuid4().hex
        try:
            ftp.storbinary('STOR '+name,io.BytesIO(b'CCDC permission probe\n'))
        except ftplib.error_perm: pass
        else:
            try: ftp.delete(name)
            except ftplib.all_errors: pass
            return 'DOWN','Inventory account can upload files'
    with ftplib.FTP() as anonymous:
        anonymous.connect(s['host'],21,timeout=5)
        try:
            size=0
            anonymous.login(); anonymous.retrbinary('RETR '+s['file'],collect)
        except ftplib.error_perm: return 'PASS','Exact inventory retrieved; upload and anonymous retrieval denied'
    return 'DOWN','Anonymous clients can retrieve inventory'


class DirectHTTPS(http.client.HTTPSConnection):
    def __init__(self,s):
        self.address=s['host']
        super().__init__(s['server_name'],443,timeout=5,context=ssl.create_default_context(cafile=s['ca_file']))
    def connect(self):
        raw=socket.create_connection((self.address,443),self.timeout)
        try: self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception: raw.close(); raise


def https_upgrade(s):
    with closing(DirectHTTPS(s)) as conn:
        conn.request('GET',s['path']); response=conn.getresponse(); body=response.read(1024*1024+1)
        import scorer
        status,reason=scorer.validate_page(response.status,body,s['expected'])
        if status!='PASS': return status,reason
    with closing(http.client.HTTPConnection(s['host'],80,timeout=5)) as conn:
        conn.request('GET',s['path'],headers={'Host':s['server_name']}); response=conn.getresponse()
        location=response.getheader('Location','')
        if response.status not in {301,302,307,308} or location!='https://'+s['server_name']+s['path']:
            return 'DOWN','HTTP does not redirect to the required HTTPS origin'
    return 'PASS','Trusted TLS name, forum content and HTTP redirect verified'


class DirectSMTP(smtplib.SMTP):
    def __init__(self,s):
        self.address=s['host']
        super().__init__(s['server_name'],587,timeout=5)
    def _get_socket(self,host,port,timeout):
        return socket.create_connection((self.address,port),timeout,self.source_address)


class DirectIMAP(imaplib.IMAP4_SSL):
    def __init__(self,s,context):
        self.address=s['host']
        super().__init__(s['server_name'],993,ssl_context=context,timeout=5)
    def _create_socket(self,timeout):
        raw=socket.create_connection((self.address,self.port),timeout)
        try: return self.ssl_context.wrap_socket(raw,server_hostname=self.host)
        except Exception: raw.close(); raise


def mail_alias(s):
    # TLS name validation is mandatory for both authenticated connections.
    context=ssl.create_default_context(cafile=s['ca_file'])
    token='ccdc-score-'+uuid.uuid4().hex
    # Connect to the defended IP while retaining certificate hostname validation.
    sender=s.get('sender',s['username'])
    with DirectSMTP(s) as smtp:
        smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo(); smtp.login(s['username'],s['password'])
        smtp.sendmail(sender,s['recipient'],f'From: {sender}\r\nTo: {s["recipient"]}\r\nSubject: {token}\r\nX-CCDC-Probe: {token}\r\n\r\nAutomated lab alias delivery check.\r\n')
    with DirectIMAP(s,context) as mailbox:
        mailbox.login(s['username'],s['password']); mailbox.select('INBOX')
        end=time.monotonic()+8
        while True:
            mailbox.noop()
            status,items=mailbox.uid('search',None,'HEADER','X-CCDC-Probe',token)
            if status=='OK' and items and items[0]: break
            if time.monotonic()>=end: break
            time.sleep(1)
        if status!='OK' or not items or not items[0]: return 'DOWN','Fresh alias message has not arrived'
        # Mark only the uniquely tagged probe message deleted. Never expunge other mail.
        for uid in items[0].split(): mailbox.uid('store',uid,'+FLAGS.SILENT','(\\Deleted)')
    return 'PASS','Authenticated TLS submission and alias delivery verified'


def http_resource(s):
    if s['scheme']=='https':
        conn=http.client.HTTPSConnection(s['host'],s['port'],timeout=5,context=ssl.create_default_context(cafile=s['ca_file']))
    else: conn=http.client.HTTPConnection(s['host'],s['port'],timeout=5)
    with closing(conn):
        conn.request('GET',s['path'],headers={'Cache-Control':'no-cache','User-Agent':'Summit-CCDC-Scorer/2.0'})
        response=conn.getresponse()
        if response.status!=200: return 'DOWN','Required resource did not return HTTP 200'
        digest=hashlib.sha256(); size=0; end=time.monotonic()+10
        while True:
            chunk=response.read1(65536)
            if not chunk: break
            size+=len(chunk)
            if size>1024*1024 or time.monotonic()>end: return 'DOWN','Resource transfer exceeds limit'
            digest.update(chunk)
        if digest.hexdigest()!=s['sha256']: return 'DOWN','Published resource does not match the supplied fixture'
    return 'PASS','Exact published fixture and required web endpoint verified'


PROBES={'dns_record':dns_record,'ftp_share':ftp_share,'https_upgrade':https_upgrade,'mail_alias':mail_alias,'http_resource':http_resource}


def run_probe(service):
    try: return PROBES[service['probe']](service)
    except ssl.SSLError: return 'DOWN','TLS negotiation or certificate verification failed'
    except (FileNotFoundError,KeyError,ValueError): return 'INVALID','Private probe configuration or trust file is unavailable'
    except Exception: return 'DOWN','Functional service check failed; review task requirements and endpoint availability'
