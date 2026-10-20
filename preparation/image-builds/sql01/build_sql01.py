#!/usr/bin/env python3
"""Recoverable SQL01 competition construction, executed from a private payload."""
import argparse,hashlib,json,os,pathlib,pwd,re,secrets,shutil,signal,socket,subprocess,sys,tempfile,time,zipfile
from contract import require_matrix,require_report
import probes
SOURCE=pathlib.Path(__file__).resolve().parent
RUNTIME=pathlib.Path('/opt/summit-sql01')
PUBLIC=pathlib.Path('/srv/summit-sql01')
ENGINE=pathlib.Path('/opt/aeacus')
IDENTITIES=('jwang','alex.admin@corp.summit.test','taylor.admin@corp.summit.test')
SERVICE_UNITS=('avahi-daemon.service','avahi-daemon.socket','cups.service','cups.socket','cups.path')
SSH=pathlib.Path('/etc/ssh/sshd_config.d/00-00-summit-sql01.conf')
MYSQL=pathlib.Path('/etc/mysql/mariadb.conf.d/99-summit-sql01.cnf')
JOURNAL=pathlib.Path('/etc/systemd/journald.conf.d/99-summit-sql01.conf')
GROUP_GRANT=pathlib.Path('/etc/sudoers.d/summit-sql01-employee')
DIRECT_GRANT=pathlib.Path('/etc/sudoers.d/summit-sql01-contractor')
CRON=pathlib.Path('/etc/cron.d/summit-sql01-marker')
PAYLOAD=pathlib.Path('/usr/local/lib/summit-sql01')
TIMER=pathlib.Path('/etc/systemd/system/summit-sql01-marker.timer')
MARKER=pathlib.Path('/etc/systemd/system/summit-sql01-marker.service')
SCORER=pathlib.Path('/etc/systemd/system/summit-sql01-aeacus.service')
SYSCTL=pathlib.Path('/etc/sysctl.d/99-zz-summit-sql01.conf')
PROFILE=pathlib.Path('/etc/profile.d/summit-sql01-training.sh')
SYSCTL_KEYS=('fs.protected_hardlinks','fs.protected_symlinks','kernel.kptr_restrict','kernel.dmesg_restrict')
STATE=None
RECORD=None

def cmd(args,timeout=90):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if RECORD:
        with (RECORD/'commands.log').open('a') as f:
            # Query arguments may include generated SQL credentials. Log only command name.
            f.write(args[0]+' exit='+str(p.returncode)+'\n'+p.stdout+p.stderr+'\n')
    if p.returncode:
        if args[0]=='systemctl': raise RuntimeError('systemctl '+ ' '.join(args[1:])+' failed: '+p.stderr.strip()[:500])
        raise RuntimeError(args[0]+' failed; see private commands.log')
    return p.stdout

def sql(query): return cmd(['mariadb','--batch','--skip-column-names','-e',query]).strip()
def put(path,text,mode=0o644):
    path=pathlib.Path(path)
    if path.is_symlink(): raise RuntimeError('Symlink refused: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8',newline='\n'); path.chmod(mode); os.chown(path,0,0)

def state_save():
    put(RECORD/'state.json',json.dumps(STATE,indent=2)+'\n',0o600)

def link_behavior(number,protected):
    # Exercise the running kernel under ordinary real UIDs, independently of the source-file check.
    scratch=pathlib.Path(tempfile.mkdtemp(prefix='summit-sql01-link-')); scratch.chmod(0o755)
    try:
        target=scratch/'root-data'; put(target,'Synthetic link-protection rehearsal.\n',0o644)
        shared=scratch/'shared'; shared.mkdir(); shared.chmod(0o1777)
        if number==23:
            code='import os,sys; os.link(sys.argv[1],sys.argv[2])'
            args=['runuser','-u','summit_employee','--','python3','-c',code,str(target),str(shared/'hardlink')]
        else:
            cmd(['runuser','-u','summit_employee','--','python3','-c','import os,sys; os.symlink(sys.argv[1],sys.argv[2])',str(target),str(shared/'symlink')])
            args=['runuser','-u','summit_contractor','--','python3','-c','import sys; open(sys.argv[1]).read()',str(shared/'symlink')]
        result=subprocess.run(args,text=True,capture_output=True,timeout=20)
        if protected and (result.returncode==0 or not any(t in result.stderr for t in ('PermissionError','Operation not permitted'))): raise RuntimeError('Kernel link denial not demonstrated')
        if not protected and result.returncode!=0: raise RuntimeError('Weak kernel link state not demonstrated')
    finally: shutil.rmtree(scratch)

def units_snapshot():
    return {n:dict(line.split('=',1) for line in cmd(['systemctl','show',n,'-p','ActiveState','-p','UnitFileState']).splitlines() if '=' in line) for n in SERVICE_UNITS}

def data_fingerprint():
    tables=sql("SELECT CONCAT('`',TABLE_SCHEMA,'`.`',TABLE_NAME,'`') FROM information_schema.tables WHERE TABLE_SCHEMA IN ('summit_shop','forum') AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA,TABLE_NAME;")
    if not tables or '`summit_shop`.`products`' not in tables or '`forum`.`phpbb_users`' not in tables: raise RuntimeError('Expected shop/forum business tables unavailable')
    values=sql('CHECKSUM TABLE '+','.join(tables.splitlines())+' EXTENDED;')
    if '\tNULL' in values: raise RuntimeError('Cannot fingerprint business data')
    return hashlib.sha256(values.encode()).hexdigest()

def preservation():
    for unit in ('mariadb','ssh','sssd'):
        cmd(['systemctl','is-active','--quiet',unit])
    cmd(['adcli','testjoin','--domain=corp.summit.test'])
    cmd(['sssctl','config-check'])
    cmd(['/usr/sbin/sshd','-t'])
    rights=cmd(['sudo','-l','-U','jwang'])
    if '(ALL : ALL) ALL' not in rights: raise RuntimeError('Local recovery sudo rights changed')
    for name in IDENTITIES: cmd(['id',name])
    for user,host,db in (('shop_app','10.77.30.10','summit_shop'),('forum_app','10.77.30.20','forum')):
        grants=set(sql("SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=\"'"+user+"'@'"+host+"'\" AND TABLE_SCHEMA='"+db+"';").splitlines())
        if not {'SELECT','INSERT','UPDATE','DELETE'}<=grants: raise RuntimeError('Application rights changed')
    if sql('SELECT @@GLOBAL.bind_address;')!='10.77.50.20': raise RuntimeError('Database listener changed')
    if STATE and data_fingerprint()!=STATE['business_hash']: raise RuntimeError('Business data changed during rehearsal; stop and inspect')

def prepare():
    global RECORD,STATE
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='sql01': raise RuntimeError('Root on SQL01 required')
    if SOURCE.stat().st_uid!=0 or SOURCE.stat().st_mode & 0o077: raise RuntimeError('Use packaged entry point')
    if 'VERSION_ID="22.3"' not in pathlib.Path('/etc/os-release').read_text(): raise RuntimeError('Expected inventoried Mint 22.3')
    for previous in pathlib.Path('/var/backups').glob('summit-sql01-competition-*'):
        if (previous/'state.json').is_file():
            phase=json.loads((previous/'state.json').read_text()).get('phase')
            if phase!='rollback-verified': raise RuntimeError('Prior build requires inspection before rerun: '+str(previous))
    for p in (RUNTIME,PUBLIC,ENGINE,PAYLOAD,SSH,MYSQL,JOURNAL,GROUP_GRANT,DIRECT_GRANT,CRON,TIMER,MARKER,SCORER,SYSCTL,PROFILE,pathlib.Path('/var/lib/summit-sql01-marker'),pathlib.Path('/home/jwang/sql01-competition-completion.json')):
        if p.exists() or p.is_symlink(): raise RuntimeError('Existing scenario path; do not overwrite: '+str(p))
    for name in ('summit_employee','summit_contractor','summit_marker'):
        try: pwd.getpwnam(name)
        except KeyError: pass
        else: raise RuntimeError('Account conflict '+name)
    if subprocess.run(['getent','group','summit-sql01-training'],capture_output=True).returncode==0: raise RuntimeError('Group conflict')
    if sql("SELECT COUNT(*) FROM mysql.user WHERE User='training_vendor';")!='0': raise RuntimeError('SQL user conflict')
    if 'FILE' in sql("SELECT PRIVILEGE_TYPE FROM information_schema.USER_PRIVILEGES WHERE GRANTEE=\"'shop_app'@'10.77.30.10'\";").splitlines(): raise RuntimeError('Unexpected existing shop FILE grant')
    if sql("SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=\"'forum_app'@'10.77.30.20'\" AND TABLE_SCHEMA='summit_shop';")!='0': raise RuntimeError('Unexpected existing cross-schema grant')
    if sql('SELECT COUNT(*) FROM mysql.roles_mapping;')!='0': raise RuntimeError('Existing MariaDB roles require adaptation')
    if shutil.disk_usage('/').free<2*1024**3: raise RuntimeError('Insufficient guest recovery headroom')
    for tool in ('mariadb-dump','getfacl','setfacl','unshare','mount','logger','journalctl','cron','visudo'):
        if not shutil.which(tool): raise RuntimeError('Missing dependency '+tool)
    for n in SERVICE_UNITS:
        if probes.unit(n)['ActiveState']!='active': raise RuntimeError('Service baseline changed '+n)
    preservation()
    RECORD=pathlib.Path(tempfile.mkdtemp(prefix='summit-sql01-competition-',dir='/var/backups')); RECORD.chmod(0o700)
    print('Private recovery record: '+str(RECORD),flush=True)
    STATE={'machine':'sql01','record':str(RECORD),'phase':'backup','created_users':{},'created_group':False,'db_user':False,'shop_file':False,'forum_select':False,'units':units_snapshot(),'local_infile':sql('SELECT @@GLOBAL.local_infile;'),'business_hash':data_fingerprint(),'desktop_paths':[],'sysctl':{k:cmd(['sysctl','-n',k]).strip() for k in SYSCTL_KEYS}}
    state_save()
    # Independent logical database backup is never used for automatic rollback;
    # rollback revokes only this build's extra grants and preserves current business rows.
    with (RECORD/'databases-before.sql').open('wb') as f:
        p=subprocess.run(['mariadb-dump','--all-databases','--single-transaction','--routines','--events','--triggers'],stdout=f,stderr=subprocess.PIPE,timeout=180)
    if p.returncode: raise RuntimeError('Database backup failed')
    cmd(['tar','--acls','--xattrs','--numeric-owner','-cpf',str(RECORD/'configuration-before.tar'),'-C','/','etc/ssh','etc/mysql','etc/sudoers','etc/sudoers.d','etc/sssd','etc/pam.d','etc/systemd/journald.conf'])
    STATE['phase']='backed-up'; state_save()

def create_resources():
    RUNTIME.mkdir(mode=0o700); PUBLIC.mkdir(mode=0o755); PAYLOAD.mkdir(mode=0o755)
    for path in (RUNTIME,PUBLIC,PAYLOAD): path.chmod(0o700 if path==RUNTIME else 0o755)
    for name in ('contract.py','probes.py'):
        shutil.copyfile(SOURCE/name,RUNTIME/name); (RUNTIME/name).chmod(0o600)
    for directory in ('shared','evidence','operations','questions'):
        (PUBLIC/directory).mkdir(mode=0o755); (PUBLIC/directory).chmod(0o755)
    for name in ('summit_employee','summit_contractor','summit_marker'):
        cmd(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin','--comment','Summit SQL01 competition synthetic identity',name])
        STATE['created_users'][name]=pwd.getpwnam(name).pw_uid; state_save()
        cmd(['usermod','--lock',name])
    cmd(['groupadd','summit-sql01-training']); STATE['created_group']=True; state_save()
    cmd(['gpasswd','-a','summit_employee','summit-sql01-training'])
    marker_dir=pathlib.Path('/var/lib/summit-sql01-marker')
    if marker_dir.exists() or marker_dir.is_symlink(): raise RuntimeError('Marker directory conflict')
    marker_dir.mkdir(mode=0o700); os.chown(marker_dir,pwd.getpwnam('summit_marker').pw_uid,65534)
    marker_body="from pathlib import Path\nPath('/var/lib/summit-sql01-marker/observed.txt').write_text('Harmless SQL01 competition marker; no network or business access.\\n')\n"
    metadata={'backup_hash':hashlib.sha256(b'Summit Supply retained catalog backup: three fictional products.\n').hexdigest(),
              'credential_marker':'SUMMIT_FICTIONAL_SQL_CREDENTIAL_'+secrets.token_hex(12),
              'media_marker':'SUMMIT_UNAUTHORIZED_MEDIA_'+secrets.token_hex(12),
              'answers':{'1':'training_vendor','2':'summit-sql01-marker.timer','3':hashlib.sha256(marker_body.encode()).hexdigest()},'payload':marker_body,
              'profile_hash':hashlib.sha256(b'# Summit SQL01 retained shell startup training file.\n# This file intentionally performs no action.\n').hexdigest()}
    put(RUNTIME/'metadata.json',json.dumps(metadata,indent=2)+'\n',0o600)
    put(PUBLIC/'operations/catalog-backup.txt','Summit Supply retained catalog backup: three fictional products.\n',0o600)
    put(PUBLIC/'evidence/incident.log','2026-10-04T09:14:00Z sql01 database-audit actor=training_vendor action=unauthorized scheduled marker registration\n')
    put(PUBLIC/'evidence/retained-marker.py',marker_body)
    put(PUBLIC/'evidence/retained-timer.txt','[Unit]\nDescription=Unapproved training marker timer\n[Timer]\nOnBootSec=10min\nOnUnitActiveSec=10min\nUnit=summit-sql01-marker.service\n[Install]\nWantedBy=timers.target\n')
    put(PUBLIC/'evidence/retained-service.txt','[Service]\nType=oneshot\nUser=summit_marker\nExecStart=/usr/bin/python3 /usr/local/lib/summit-sql01/timer-marker.py\n')
    questions=[('Which database account is attributed the unauthorized change in the retained incident log?','/srv/summit-sql01/evidence/incident.log','Account name, case insensitive.'),
               ('What is the complete name of the unauthorized systemd TIMER unit?','/srv/summit-sql01/evidence/retained-timer.txt','Unit name including .timer, case insensitive.'),
               ('What is the SHA-256 of the retained harmless marker payload?','/srv/summit-sql01/evidence/retained-marker.py','64 hexadecimal characters, case insensitive.')]
    for i,(q,e,f) in enumerate(questions,1):
        path=PUBLIC/'questions'/('Question-'+str(i)+'.txt')
        put(path,'Forensic Question '+str(i)+'\n\nQuestion: '+q+'\nEvidence: '+e+'\nAnswer format: '+f+'\n\nAnswer:\n\n',0o660)
        cmd(['setfacl','-m',','.join('u:'+n+':rw' for n in IDENTITIES),str(path)])
        for n in IDENTITIES:
            # Real NSS identity is used to prove reading and saving without changing the blank answer.
            cmd(['runuser','-u',n,'--','python3','-c','from pathlib import Path; p=Path(__import__("sys").argv[1]); t=p.read_text(); p.write_text(t)',str(path)])
    answers=RECORD/'private-answers'; answers.mkdir(mode=0o700)
    for i in range(1,4): put(answers/('Question-'+str(i)+'.txt'),'Answer:\n'+metadata['answers'][str(i)]+'\n',0o600)
    wrong=RECORD/'wrong-answers'; wrong.mkdir(mode=0o700)
    for i in range(1,4): put(wrong/('Question-'+str(i)+'.txt'),'Answer:\ndeliberately incorrect\n',0o600)
    ENGINE.mkdir(mode=0o755); ENGINE.chmod(0o755)
    digest=hashlib.sha256((SOURCE/'aeacus-linux-v2.1.1.zip').read_bytes()).hexdigest()
    if digest!='bd75e05505bd1a1e288b0453a4611ad88f6794dd54063db16485e0328c69f149': raise RuntimeError('Engine archive checksum mismatch')
    with zipfile.ZipFile(SOURCE/'aeacus-linux-v2.1.1.zip') as archive:
        for member in archive.infolist():
            parts=pathlib.PurePosixPath(member.filename).parts
            if not parts or parts[0]!='aeacus-linux' or '..' in parts or pathlib.PurePosixPath(member.filename).is_absolute(): raise RuntimeError('Unsafe engine archive member')
            if (member.external_attr>>16)&0o170000==0o120000: raise RuntimeError('Engine symlink refused')
            if member.file_size>100*1024**2: raise RuntimeError('Oversized engine member')
            if len(parts)==1: continue
            target=ENGINE.joinpath(*parts[1:])
            if member.is_dir(): target.mkdir(parents=True,exist_ok=True); target.chmod(0o755)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(member)); target.chmod(0o644)
    for name in ('aeacus','phocus'): (ENGINE/name).chmod(0o700)
    put(ENGINE/'TeamID.txt','SUMMIT-SQL01-PRACTICE\n',0o644)
    put(ENGINE/'ReadMe.conf',(SOURCE/'README.html').read_text(),0o600)
    put(ENGINE/'scoring.conf',(SOURCE/'scoring.conf').read_text(),0o600)
    put(PUBLIC/'README.html',(SOURCE/'README.html').read_text())
    STATE['phase']='resources'; state_save()

def ssh_state(protected):
    put(SSH,'PermitRootLogin '+('no' if protected else 'yes')+'\nPermitEmptyPasswords '+('no' if protected else 'yes')+'\nX11Forwarding '+('no' if protected else 'yes')+'\nMaxAuthTries '+('3' if protected else '6')+'\nAllowAgentForwarding '+('no' if protected else 'yes')+'\nAllowTcpForwarding '+('no' if protected else 'yes')+'\nPermitUserEnvironment '+('no' if protected else 'yes')+'\nLogLevel '+('VERBOSE' if protected else 'INFO')+'\n')
    cmd(['/usr/sbin/sshd','-t']); cmd(['systemctl','reload','ssh'])

def cron_state(protected):
    path=PAYLOAD/'cron-marker.py'
    if protected:
        CRON.unlink(missing_ok=True); path.unlink(missing_ok=True)
    else:
        put(path,json.loads((RUNTIME/'metadata.json').read_text())['payload'])
        put(CRON,'*/10 * * * * summit_marker /usr/bin/python3 /usr/local/lib/summit-sql01/cron-marker.py\n')
        cmd(['runuser','-u','summit_marker','--','python3',str(path)])

def timer_state(protected):
    names=['summit-sql01-marker.timer','summit-sql01-marker.service']
    path=PAYLOAD/'timer-marker.py'
    if protected:
        if TIMER.exists(): cmd(['systemctl','stop',names[0]]); cmd(['systemctl','disable',names[0]])
        if MARKER.exists(): cmd(['systemctl','stop',names[1]])
        TIMER.unlink(missing_ok=True); MARKER.unlink(missing_ok=True); path.unlink(missing_ok=True)
        cmd(['systemctl','daemon-reload'])
    else:
        put(path,json.loads((RUNTIME/'metadata.json').read_text())['payload'])
        put(TIMER,(PUBLIC/'evidence/retained-timer.txt').read_text())
        put(MARKER,'[Unit]\nDescription=Inert SQL01 competition marker\n[Service]\nType=oneshot\nUser=summit_marker\nGroup=nogroup\nExecStart=/usr/bin/python3 /usr/local/lib/summit-sql01/timer-marker.py\nStateDirectory=summit-sql01-marker\nNoNewPrivileges=yes\nPrivateNetwork=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=yes\nCapabilityBoundingSet=\nRestrictAddressFamilies=AF_UNIX\nReadWritePaths=/var/lib/summit-sql01-marker\n')
        cmd(['systemctl','daemon-reload'])
        cmd(['systemctl','enable','--now','summit-sql01-marker.timer'])
        # Bounded controlled marker run proves installed payload works under its sandbox.
        cmd(['systemctl','start','summit-sql01-marker.service'])
        observed=pathlib.Path('/var/lib/summit-sql01-marker/observed.txt').read_text()
        if not observed.startswith('Harmless SQL01'): raise RuntimeError('Marker behavior failed')

def service_state(names,protected):
    if protected:
        # Desktop D-Bus/socket clients can replace pending stop jobs while activation
        # remains available. Remove boot/alias activation and mask before stopping.
        cmd(['systemctl','disable']+list(names))
        cmd(['systemctl','mask']+list(names))
        cmd(['systemctl','stop']+list(names))
    else:
        cmd(['systemctl','unmask']+list(names)); cmd(['systemctl','enable']+list(names)); cmd(['systemctl','start']+list(names))

def journal_state(protected):
    put(JOURNAL,'[Journal]\nStorage='+('persistent' if protected else 'volatile')+'\n')
    if protected: pathlib.Path('/var/log/journal').mkdir(exist_ok=True)
    cmd(['systemctl','restart','systemd-journald'])
    cmd(['logger','-t','summit-sql01-rehearsal','SQL01 journald scenario checkpoint'])
    if protected: cmd(['journalctl','--flush'])

def set_state(number,protected):
    if number==1:
        put(MYSQL,'[mysqld]\nlocal_infile='+('0' if protected else '1')+'\n')
        sql('SET GLOBAL local_infile='+('0' if protected else '1')+';')
    elif number==2:
        if protected:
            if STATE['db_user']: sql("DROP USER IF EXISTS 'training_vendor'@'localhost';"); STATE['db_user']=False; state_save()
        else:
            if not STATE['db_user']:
                sql("CREATE USER 'training_vendor'@'localhost' IDENTIFIED BY '"+secrets.token_urlsafe(36)+"' ACCOUNT LOCK;")
                STATE['db_user']=True; state_save()
    elif number==3:
        if protected:
            if STATE['shop_file']: sql("REVOKE FILE ON *.* FROM 'shop_app'@'10.77.30.10';"); STATE['shop_file']=False; state_save()
        else:
            sql("GRANT FILE ON *.* TO 'shop_app'@'10.77.30.10';"); STATE['shop_file']=True; state_save()
    elif number==4:
        if protected:
            if STATE['forum_select']: sql("REVOKE SELECT ON summit_shop.* FROM 'forum_app'@'10.77.30.20';"); STATE['forum_select']=False; state_save()
        else:
            sql("GRANT SELECT ON summit_shop.* TO 'forum_app'@'10.77.30.20';"); STATE['forum_select']=True; state_save()
    elif number in (5,6,7,18,19,20,21,22): ssh_state(protected)
    elif number in (8,9):
        path=GROUP_GRANT if number==8 else DIRECT_GRANT
        if protected: path.unlink(missing_ok=True)
        else: put(path,('%summit-sql01-training' if number==8 else 'summit_contractor')+' ALL=(ALL:ALL) NOPASSWD: ALL\n',0o440)
        cmd(['visudo','-c'])
        identity='summit_employee' if number==8 else 'summit_contractor'
        attempt=subprocess.run(['runuser','-u',identity,'--','sudo','-n','/usr/bin/id','-u'],text=True,capture_output=True,timeout=20)
        if protected and attempt.returncode==0: raise RuntimeError('Excess sudo remains effective for '+identity)
        if not protected and (attempt.returncode!=0 or attempt.stdout.strip()!='0'): raise RuntimeError('Seeded sudo privilege not effective for '+identity)
    elif number==10:
        p=PUBLIC/'operations/catalog-backup.txt'; cmd(['setfacl','-b',str(p)]); p.chmod(0o600 if protected else 0o666)
    elif number==11: cron_state(protected)
    elif number==12: timer_state(protected)
    elif number in (13,14):
        metadata=json.loads((RUNTIME/'metadata.json').read_text())
        path=PUBLIC/'shared'/('legacy-passwords.txt' if number==13 else 'personal-media.txt')
        if protected: path.unlink(missing_ok=True)
        else: put(path,metadata['credential_marker' if number==13 else 'media_marker']+'\nFictional competition material only.\n')
    elif number in (15,16): service_state(('avahi-daemon.service','avahi-daemon.socket') if number==15 else ('cups.service','cups.socket','cups.path'),protected)
    elif number==17: journal_state(protected)
    elif number in (23,24,25,26):
        # Source the unchanged sibling values from live state so each kernel control is independent.
        values={k:cmd(['sysctl','-n',k]).strip() for k in SYSCTL_KEYS}
        values[SYSCTL_KEYS[number-23]]='1' if protected else '0'
        put(SYSCTL,''.join(k+'='+v+'\n' for k,v in values.items()))
        cmd(['sysctl','-w',SYSCTL_KEYS[number-23]+'='+('1' if protected else '0')])
        if number in (23,24): link_behavior(number,protected)
    elif number==27:
        put(PROFILE,'# Summit SQL01 retained shell startup training file.\n# This file intentionally performs no action.\n',0o644 if protected else 0o666)
        cmd(['setfacl','-b',str(PROFILE)])

def matrix(label,expected,answer_root=None):
    states=[probes.verdict(i,answer_root) for i in range(1,31)]
    put(RECORD/(label+'.json'),json.dumps({'states':states,'expected':expected,'time':time.time()},indent=2)+'\n',0o600)
    require_matrix(states,expected); preservation()
    return states

def engine_score(label,score):
    (ENGINE/'assets/previous.txt').unlink(missing_ok=True)
    report=ENGINE/'assets/ScoringReport.html'; report.unlink(missing_ok=True)
    cmd([str(ENGINE/'aeacus'),'--dir',str(ENGINE)+'/', 'score'],timeout=180)
    html=report.read_text(); require_report(html,score)
    put(RECORD/(label+'.html'),html,0o600)

def private_engine():
    # Production engine fixes /opt/aeacus; bind only inside a private mount namespace.
    candidate=RECORD/'candidate'; shutil.copytree(ENGINE,candidate)
    report=candidate/'assets/ScoringReport.html'; report.unlink(missing_ok=True)
    code="import os,subprocess,sys; subprocess.run(['mount','--bind',sys.argv[1],'/opt/aeacus'],check=True); os.chdir('/opt/aeacus'); os.execv('/opt/aeacus/phocus',['/opt/aeacus/phocus'])"
    with (RECORD/'private-phocus.log').open('wb') as log:
        p=subprocess.Popen(['unshare','--mount','--propagation','private','python3','-c',code,str(candidate)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try: wait_report(report,lambda:p.poll() is None,0)
        finally:
            try: os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=5)

def wait_report(path,alive,score):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        if not alive(): raise RuntimeError('Phocus stopped during report verification')
        if path.exists():
            try: require_report(path.read_text(),score); return
            except ValueError: pass
        time.sleep(0.25)
    raise RuntimeError('Fresh encrypted report timed out')

def desktop_links():
    for name in IDENTITIES:
        identity=pwd.getpwnam(name); home=pathlib.Path(identity.pw_dir)
        if not home.exists():
            home.mkdir(mode=0o700); os.chown(home,identity.pw_uid,identity.pw_gid)
            STATE['desktop_paths'].append({'path':str(home),'directory':True}); state_save()
        desktop=home/'Desktop'
        if not desktop.exists():
            desktop.mkdir(mode=0o700); os.chown(desktop,identity.pw_uid,identity.pw_gid)
            STATE['desktop_paths'].append({'path':str(desktop),'directory':True}); state_save()
        files=[('SQL01-README',PUBLIC/'README.html','web'),('SQL01-Score',ENGINE/'assets/ScoringReport.html','web')]
        files += [('SQL01-Question-'+str(i),PUBLIC/'questions'/('Question-'+str(i)+'.txt'),'text') for i in range(1,4)]
        for title,target,kind in files:
            path=desktop/(title+'.desktop')
            if path.exists() or path.is_symlink(): raise RuntimeError('Desktop shortcut conflict')
            app='/usr/bin/xed' if kind=='text' else '/usr/bin/xdg-open'
            put(path,'[Desktop Entry]\nType=Application\nName='+title+'\nExec='+app+' '+str(target)+'\nIcon='+('text-x-generic' if kind=='text' else 'text-html')+'\nTerminal=false\n',0o755)
            os.chown(path,identity.pw_uid,identity.pw_gid)
            STATE['desktop_paths'].append({'path':str(path),'directory':False}); state_save()
            cmd(['runuser','-u',name,'--','test','-r',str(target)])
    put(PUBLIC/'Acceptance.html','<html><body><h1>SQL01 release acceptance</h1><p>Automated rehearsals and encrypted scoring must be verified in the organizer receipt.</p><ul><li>PENDING: real local and domain login, console recovery and SSH preservation.</li><li>PENDING: launch all forensic desktop icons, save each answer, and confirm credit under every supported identity.</li><li>PENDING: shop order and forum read/write workflows from their actual source hosts.</li><li>PENDING: approved reboot, scorer persistence and snapshot restoration.</li><li>PENDING: organizer archive handling and VM export.</li></ul></body></html>')

def rollback():
    # Only fixed scenario-owned targets and recorded synthetic identities are reverted.
    # Original configuration archives and business dumps remain untouched.
    if not STATE or STATE['phase']=='backed-up': return
    if SCORER.exists(): cmd(['systemctl','disable','--now','summit-sql01-aeacus.service'])
    if TIMER.exists(): cmd(['systemctl','disable','--now','summit-sql01-marker.timer'])
    if MARKER.exists(): cmd(['systemctl','stop','summit-sql01-marker.service'])
    for i in (2,3,4): set_state(i,True)
    sql('SET GLOBAL local_infile='+STATE['local_infile']+';')
    for p in (SSH,MYSQL,JOURNAL,GROUP_GRANT,DIRECT_GRANT,CRON,TIMER,MARKER,SCORER,SYSCTL,PROFILE): p.unlink(missing_ok=True)
    for k,v in STATE['sysctl'].items(): cmd(['sysctl','-w',k+'='+v])
    cmd(['/usr/sbin/sshd','-t']); cmd(['systemctl','reload','ssh']); cmd(['systemctl','daemon-reload']); cmd(['systemctl','restart','systemd-journald'])
    for name,saved in STATE['units'].items():
        cmd(['systemctl','unmask',name])
        cmd(['systemctl','enable' if saved['UnitFileState']=='enabled' else 'disable',name])
    for name,saved in STATE['units'].items(): cmd(['systemctl','start' if saved['ActiveState']=='active' else 'stop',name])
    for name,uid in STATE['created_users'].items():
        current=pwd.getpwnam(name)
        if current.pw_uid!=uid or current.pw_gecos!='Summit SQL01 competition synthetic identity': raise RuntimeError('Synthetic identity changed; rollback stopped')
        cmd(['userdel',name])
    if STATE['created_group']: cmd(['groupdel','summit-sql01-training'])
    for item in reversed(STATE['desktop_paths']):
        p=pathlib.Path(item['path'])
        if item['directory']:
            if p.exists() and not any(p.iterdir()): p.rmdir()
        else: p.unlink(missing_ok=True)
    for p in (RUNTIME,PUBLIC,ENGINE,PAYLOAD,pathlib.Path('/var/lib/summit-sql01-marker')):
        if p.is_symlink(): raise RuntimeError('Rollback tree substituted')
        if p.exists(): shutil.rmtree(p)
    preservation()
    if units_snapshot()!=STATE['units']: raise RuntimeError('Original service states did not restore')
    STATE['phase']='rollback-verified'; state_save()

def main():
    os.umask(0o077)
    os.chdir(SOURCE)
    prepare()
    try:
        STATE['phase']='creating'; state_save(); create_resources()
        cmd([str(ENGINE/'aeacus'),'version'])
        cmd([str(ENGINE/'aeacus'),'--dir',str(ENGINE)+'/', 'check'])
        # readme has a v2.1.1 cwd requirement, unlike its --dir-aware commands.
        os.chdir(ENGINE); cmd([str(ENGINE/'aeacus'),'readme']); os.chdir(SOURCE)
        for i in range(1,28):
            set_state(i,True)
            if probes.verdict(i)!='PASS': raise RuntimeError('Protected probe failed: '+str(i))
            preservation()
            set_state(i,False)
            if probes.verdict(i)!='FAIL': raise RuntimeError('Planted probe failed: '+str(i))
            preservation()
            set_state(i,True)
            if probes.verdict(i)!='PASS': raise RuntimeError('Repaired probe failed: '+str(i))
            set_state(i,False)
            if probes.verdict(i)!='FAIL': raise RuntimeError('Restored probe failed: '+str(i))
            with (RECORD/'control-matrix.jsonl').open('a') as f: f.write(json.dumps({'id':i,'states':['PASS','FAIL','PASS','FAIL']})+'\n')
            print('Rehearsed '+str(i)+'/30',flush=True)
        for i in (28,29,30):
            if probes.verdict(i)!='FAIL' or probes.verdict(i,RECORD/'wrong-answers')!='FAIL' or probes.verdict(i,RECORD/'private-answers')!='PASS': raise RuntimeError('Forensics rehearsal failed')
        matrix('combined-start','FAIL'); engine_score('starting-score',0)
        for i in range(1,28): set_state(i,True)
        # An explicit private test adapter selects private answers without filling public files.
        original=(ENGINE/'scoring.conf').read_text()
        test_config=original.replace('probes.py ', 'solution_adapter.py ')
        adapter='import sys\nfrom probes import verdict\nprint(verdict(int(sys.argv[1]),'+repr(str(RECORD/'private-answers'))+'))\n'
        put(RUNTIME/'solution_adapter.py',adapter,0o600)
        put(ENGINE/'scoring.conf',test_config,0o600)
        matrix('combined-solution','PASS',RECORD/'private-answers'); engine_score('solution-score',100)
        put(ENGINE/'scoring.conf',original,0o600); (RUNTIME/'solution_adapter.py').unlink()
        for i in range(1,28): set_state(i,False)
        matrix('combined-restored','FAIL'); engine_score('restored-score',0)
        cmd([str(ENGINE/'aeacus'),'--dir',str(ENGINE)+'/', 'encrypt'])
        if not (ENGINE/'scoring.dat').is_file() or (ENGINE/'scoring.dat').stat().st_size<100: raise RuntimeError('Ciphertext missing')
        (ENGINE/'scoring.dat').chmod(0o600)
        shutil.copyfile(ENGINE/'scoring.conf',RECORD/'organizer-scoring.conf')
        (ENGINE/'scoring.conf').unlink(); private_engine()
        report=ENGINE/'assets/ScoringReport.html'; report.unlink(missing_ok=True)
        put(SCORER,'[Unit]\nDescription=SQL01 competition encrypted Aeacus\nAfter=network.target mariadb.service ssh.service sssd.service\n[Service]\nType=simple\nUser=root\nWorkingDirectory=/opt/aeacus\nExecStart=/opt/aeacus/phocus\nRestart=on-failure\nRestartSec=10\nUMask=0022\n[Install]\nWantedBy=multi-user.target\n')
        cmd(['systemctl','daemon-reload']); cmd(['systemctl','enable','--now','summit-sql01-aeacus.service'])
        wait_report(report,lambda:subprocess.run(['systemctl','is-active','--quiet','summit-sql01-aeacus.service']).returncode==0,0)
        report.chmod(0o644); (ENGINE/'assets/ReadMe.html').chmod(0o644)
        desktop_links(); matrix('production-state','FAIL')
        STATE['phase']='runtime-verified'; state_save()
        manifest=json.loads((SOURCE/'competition-manifest.json').read_text())
        manifest['status']='runtime-verified'; manifest['guest_rehearsals']='passed'
        manifest['recovery_record']=str(RECORD)
        manifest['scoring']['deployed_report']=str(report)
        manifest['scoring']['observed_scores']={'start':0,'solution':100,'restored':0,'encrypted_runtime':0}
        manifest['fingerprints']={name:hashlib.sha256((RUNTIME/name).read_bytes()).hexdigest() for name in ('probes.py','contract.py','metadata.json')}
        for issue in manifest['issues']:
            issue['status']='runtime-verified'
            issue['evidence']=['protected PASS, planted FAIL, repaired PASS, final planted FAIL' if issue['id']<=27 else 'public blank FAIL and private correct-answer PASS',str(RECORD/'combined-solution.json'),str(RECORD/'combined-restored.json')]
        put(RECORD/'competition-manifest.json',json.dumps(manifest,indent=2)+'\n',0o600)
        receipt={'status':'runtime-verified','points':0,'total':100,'checks':30,'recovery':str(RECORD),'manual_acceptance':'PENDING','export':'PENDING'}
        put(RECORD/'completion.json',json.dumps(receipt,indent=2)+'\n',0o600)
        export=pathlib.Path('/home/jwang/sql01-competition-completion.json')
        if export.exists() or export.is_symlink(): raise RuntimeError('Existing completion export preserved')
        put(export,json.dumps(receipt,indent=2)+'\n',0o600); identity=pwd.getpwnam('jwang'); os.chown(export,identity.pw_uid,identity.pw_gid)
        # Organizer build/solution sources are not part of the participant interface.
        entry=pathlib.Path('/home/jwang/make-sql01-competition.sh')
        if entry.is_file() and not entry.is_symlink():
            shutil.move(str(entry),str(RECORD/'organizer-entrypoint.sh'))
            (RECORD/'organizer-entrypoint.sh').chmod(0o600); os.chown(RECORD/'organizer-entrypoint.sh',0,0)
        print('Automated construction verified: 30 checks, 0/100 start, 100/100 solution, encrypted Phocus 0/100.',flush=True)
        print('Manual login, desktop, business-client, reboot, snapshot restore and export acceptance remain.',flush=True)
    except BaseException as error:
        put(RECORD/'failure.txt',str(error)+'\n',0o600)
        print('Build stopped; restoring owned changes. Evidence: '+str(RECORD),flush=True)
        try: rollback()
        except BaseException as recovery_error:
            put(RECORD/'rollback-failure.txt',str(recovery_error)+'\n',0o600)
            print('ROLLBACK INCOMPLETE: '+str(recovery_error),flush=True)
        raise

if __name__=='__main__': main()
