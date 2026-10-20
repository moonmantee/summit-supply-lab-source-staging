"""Prepare the mail extension of the accepted forum Windows architecture."""
import hashlib,json,pathlib,shutil
ROOT=pathlib.Path(__file__).resolve().parent
SRC=ROOT.parent/'forum01-build/caldera-package';DST=ROOT/'caldera-package'
names=['windows_worker.py','windows_services.py','windows_agent.py','windows_notice.py','Show-Notice.ps1',
 'fixture_contract.py','pilot_agent.py','pilot_cleanup.py','test_pilot_cleanup.py','contact_gateway.py',
 'test_gateway_native.py','renew_lab_pki.py','launch.py','fixture_control.py',
 'Install-Forum01.ps1','Complete-Forum01.ps1','enroll_forum01.py','enable_forum01.py','pilot_forum01.py',
 'firewall-forum01-contact.php','firewall-forum01-authorization.php']
for name in names:
 text=(SRC/name).read_text()
 if name not in ('launch.py','fixture_control.py'):
  text=text.replace('forum01','mail01').replace('FORUM01','MAIL01').replace('Forum01','Mail01').replace('forum','mail').replace('Forum','Mail')
 if name=='windows_worker.py':text=text.replace("('web','ftp')","('web','smtp','imap')")
 if name=='windows_services.py':
  text=text.replace('import urllib.request','import ssl\nimport http.client')
  start=text.index('TARGETS=');end=text.index('\nclass NativeService:')
  text=text[:start]+'''TARGETS={'web':('W3SVC',r'C:\\Windows\\System32\\inetsrv\\iisw3adm.dll'),
         'smtp':('MESMTPCS',r'C:\\Program Files (x86)\\Mail Enable\\Bin64\\MESMTPC.EXE'),
         'imap':('MEIMAPS',r'C:\\Program Files (x86)\\Mail Enable\\Bin64\\MEIMAPS.exe')}
CERT=pathlib.Path(r'C:\\ProgramData\\SummitCaldera\\app\\mail01-webmail-public.cer')
CERT_SHA256='f7e9a8f8bbac1fe7bd175c52df1959ed11e25b40ce8c508ce6c04f84558a3a03'

def application_health(target):
    try:
        if target=='web':
            raw=CERT.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=CERT_SHA256:return False
            ctx=ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(raw))
            with socket.create_connection(('127.0.0.1',443),timeout=2) as raw_socket:
                with ctx.wrap_socket(raw_socket,server_hostname='webmail.corp.summit.test') as connection:
                    connection.sendall(b'GET /Mondo/lang/sys/login.aspx HTTP/1.0\\r\\nHost: webmail.corp.summit.test\\r\\n\\r\\n')
                    response=http.client.HTTPResponse(connection);response.begin()
                    return response.status==200 and b'MailEnable' in response.read(262144)
        if target=='imap':
            with socket.create_connection(('127.0.0.1',143),timeout=2) as connection:return connection.recv(512).startswith(b'* OK')
        if target=='smtp':
            with socket.create_connection(('127.0.0.1',25),timeout=2) as connection:
                stream=connection.makefile('rwb',buffering=0)
                if not stream.readline(1024).startswith(b'220'):return False
                stream.write(b'EHLO score01.corp.summit.test\\r\\n')
                for _ in range(32):
                    line=stream.readline(2048)
                    if line.startswith(b'250 '):return True
                    if not line.startswith(b'250-'):return False
                return False
        return False
    except (OSError,ValueError,http.client.HTTPException):return False
''' +text[end:]
  start=text.index('        import winreg');end=text.index('        with self.handle() as h:',start)
  text=text[:start]+'''        if self.target=='web':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SYSTEM\\\\CurrentControlSet\\\\Services\\\\'+self.service+'\\\\Parameters') as key:
                dll=winreg.ExpandEnvironmentStrings(winreg.QueryValueEx(key,'ServiceDll')[0])
            if os.path.normcase(dll)!=os.path.normcase(self.dll):raise ValueError('Unexpected service DLL mapping')
''' +text[end:]
  text=text.replace("            raw2=self._query(h,2)","            expected=r'C:\\Windows\\System32\\svchost.exe' if self.target=='web' else self.dll\n            if self.target!='web' and os.path.normcase(cfg.binary.strip(chr(34)))!=os.path.normcase(expected):raise ValueError('Unexpected service executable')\n            raw2=self._query(h,2)")
  text=text.replace("pathlib.Path(r'C:\\Windows\\System32\\svchost.exe').read_bytes()","pathlib.Path(expected).read_bytes()")
  text=text.replace("        if not any(a[0]==1 for a in values['ftp']['failure']['actions']):raise ValueError('Missing FTP restart baseline')", "        if any(not any(a[0]==1 for a in values[target]['failure']['actions']) for target in ('smtp','imap')):raise ValueError('Missing mail restart baseline')")
 if name in ('Install-Forum01.ps1','Complete-Forum01.ps1'):
  text=text.replace("if($p.Name -like '*.py')","if($p.Name -like '*.py' -or $p.Name -like '*.cer')").replace('IIS/FTP untouched','SMTP/IMAP/IIS untouched')
 if name=='launch.py':text=text.replace("'summit-forum01':'forum01'","'summit-forum01':'forum01','summit-mail01':'mail01'")
 profiles=['mail01-popup','mail01-expiry','first3h-mail01']+[f'first3h-mail01-{target}-{phase}' for target in ('smtp','imap','web') for phase in ('stop','disable','restart-off') if (target,phase)!=('web','restart-off')]
 if name=='fixture_control.py':text=text.replace("'first3h-forum01-ftp-restart-off'))","'first3h-forum01-ftp-restart-off',"+','.join(repr(p) for p in profiles)+"))")
 if name=='enroll_forum01.py':
  text=text.replace('1a12f06bf011e7b027f457208c5a3fbd427dc72d509944c7b46f7a2ca8508e49','b95c8b147a3de2a84e46286de40ab01c28133762117c369478e9719f1d451ae2').replace('a1eecc0ef49da9f0b06850d98de0303427c2b3b94741d953d5a4bc06e1444d3b','67f884fd64350f41af2343264f5b543eff4e04d112e85c85da2a8c715a20faad')
  text=text.replace("'10.77.30.20'","'10.77.30.30'").replace("['web','ftp','desktop']","['smtp','imap','web','desktop']")
  start=text.index("    for target,phase,action in [");end=text.index('\n        write(APP/',start)
  text=text[:start]+"    for target,phase,action in [(t,p,a) for t in ('smtp','imap','web') for p,a in (('stop','business_stop'),('disable','business_disable'),('restart-off','business_restart_off')) if (t,p)!=('web','restart-off')]:"+text[end:]
 if name=='enable_forum01.py':text=text.replace("['web','ftp','desktop']","['smtp','imap','web','desktop']")
 if name=='pilot_forum01.py':
  text=text.replace('from pilot_cleanup import disarm','from pilot_cleanup import disarm\nfrom pilot_ready import wait_ready')
  text=text.replace("command('load',args.profile);command('start')","command('load',args.profile);wait_ready();command('start')")
  start=text.index("choices=(");end=text.index(');args=',start)
  text=text[:start]+"choices="+repr(tuple(p for p in profiles if p!='mail01-expiry' and p!='first3h-mail01'))+text[end:]
  text=text.replace("target='ftp' if '-ftp-' in args.profile else 'web'","target=next((t for t in ('smtp','imap','web') if '-'+t+'-' in args.profile),'web')")
  text=text.replace("s['id']=='mail01-'+target","s['id']=={'smtp':'mail01-smtp','imap':'mail01-imaps','web':'mail01-https'}[target]")
 if name.startswith('firewall-'):text=text.replace('10.77.30.20','10.77.30.30')
 name=name.replace('Forum01','Mail01').replace('forum01','mail01')
 (DST/name).write_text(text,encoding='utf-8')
events=[dict(id=f'mail-popup-{i}',guest='mail01',action='notice',target='desktop',at=i*300,window=15) for i in range(12)]
for i in range(6):events.append(dict(id=f'mail-stop-{i}',guest='mail01',action='business_stop',target=('smtp','imap','web')[i%3],at=(65+i*10)*60,window=15,duration=180))
for i,(target,action) in enumerate([('smtp','business_disable'),('imap','business_restart_off'),('web','business_disable'),('smtp','business_restart_off'),('imap','business_disable'),('web','business_disable')]):events.append(dict(id=f'mail-policy-{i}',guest='mail01',action=action,target=target,at=(125+i*10)*60,window=15,duration=180))
(DST/'first3h-mail01.json').write_text(json.dumps(events,indent=2)+'\n')
(DST/'vendor').mkdir(exist_ok=True)
shutil.copyfile(SRC/'vendor/python-3.13.16-embed-amd64.zip',DST/'vendor/python-3.13.16-embed-amd64.zip')
guest=['windows_agent.py','windows_services.py','windows_worker.py','windows_notice.py','fixture_contract.py','pilot_agent.py','Show-Notice.ps1','mail01-webmail-public.cer']
(DST/'guest-manifest.json').write_text(json.dumps({n:hashlib.sha256((DST/n).read_bytes()).hexdigest() for n in guest},indent=2)+'\n')
