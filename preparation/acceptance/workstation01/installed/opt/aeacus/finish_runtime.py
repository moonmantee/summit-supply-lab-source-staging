#!/usr/bin/env python3
"""One-command organizer controller. Root recovery data never becomes public."""
import configparser,datetime,hashlib,json,os,pathlib,pwd,re,shutil,subprocess,sys,time
ROOT=pathlib.Path('/opt/aeacus')
SHARED=pathlib.Path('/srv/summit-competition')
BACKUP=pathlib.Path('/var/backups/summit-workstation01-finish')
SETUP=pathlib.Path('/home/jwang/aeacus-setup')
VERIFY='--verify-only' in sys.argv
RES=ROOT/'helpers' if VERIFY else pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).parent
sys.path[:0]=[str(RES),str(ROOT/'probes' if VERIFY else RES/'probes')]
from finish_helpers import safe_path,ssh_repair,restore_entry,restore_training_identity,valid_zone_name,choose_finish_backup,unit_state_matches,validated_snapshot_entries,verified_receipt,private_phocus,wait_scoring_report
from auth_policy import update_policy
from application_stage import firefox_state
import access,core,policy,scenario,trust
if VERIFY:
    BACKUP=safe_path(json.loads((RES/'finish-backup.json').read_text())['path'])
    assert re.fullmatch(r'/var/backups/summit-workstation01-finish(?:-retry[0-9]+)?',str(BACKUP)),'Unexpected acceptance-record path'
USERS=('alex.admin@corp.summit.test','taylor.admin@corp.summit.test','competitor-recovery')
ZONE='summit-ws01'
AUDIT=pathlib.Path('/etc/audit/rules.d/99-summit-identity.rules')
WATCHES=('/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow','/etc/sudoers')
AUTO=pathlib.Path('/etc/dnf/automatic.conf')
AUTO_TIMER='dnf-automatic-install.timer'
TIMER_DROP=pathlib.Path('/etc/systemd/system/dnf-automatic-install.timer.d/90-summit-schedule.conf')
UNITS=('sshd.service','sssd.service','firewalld.service','auditd.service','summit-aeacus.service',
       'avahi-daemon.service','avahi-daemon.socket','cups.service','cups.socket','cups.path',
       'cockpit.socket','cockpit.service','summit-marker.timer','summit-marker.service',AUTO_TIMER,
       'summit-image-verify.service')
PENDING=['Actual repaired-policy domain/fallback login and SSH denial',
         'Controlled DC-outage local login and password-required sudo',
         'Desktop question icons, Firefox policy, screen locking and business resources',
         'Timed local unlock and real security-update application',
         'Reboot verification, snapshot restore rehearsal and final VM export']
def call(args,ok=(0,),timeout=60,input=None,cwd=None):
    p=subprocess.run([str(a) for a in args],text=True,input=input,capture_output=True,
                     timeout=timeout,cwd=cwd,env=dict(os.environ,LC_ALL='C'))
    if p.returncode not in ok:
        raise RuntimeError('Command failed: '+str(args[0])+'\n'+p.stdout+p.stderr)
    return p.stdout.strip()
def write(path,text,mode=0o644):
    path=safe_path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text); path.chmod(mode)
    call(['restorecon',str(path)])
def states():
    result={}
    for unit in UNITS:
        output=call(['systemctl','show',unit,'-p','ActiveState','-p','UnitFileState','-p','LoadState','-p','Type'],ok=(0,1,4))
        result[unit]=dict(line.split('=',1) for line in output.splitlines() if '=' in line)
    return result
def checks():
    data={i:core.evaluate(i,core.collect(i)) for i in core.ISSUES}
    for module in (access,policy,scenario,trust): data.update({i:module.check(i) for i in module.ISSUES})
    assert set(data)==set(range(1,41)),'Incomplete 40-check set'
    return data
def health(scoring=False):
    required=['sshd','sssd','firewalld']+(['summit-aeacus'] if scoring else [])
    assert call(['systemctl','is-active']+required)=='\n'.join(['active']*len(required)),'Required service unavailable'
    call(['authselect','check']); call(['visudo','-c']); call(['/usr/sbin/sshd','-t'])
    for user in USERS+('jwang',): pwd.getpwnam(user)
    assert 'corp.summit.test' in call(['realm','list','--name-only']).splitlines(),'Domain join missing'
def public_status(automated,details):
    import html
    body='<h1>Workstation01 image acceptance</h1><p>'+html.escape(details)+'</p>'
    body+='<p>Automated checks: '+('passed' if automated else 'needs attention')+'</p><p>Pending acceptance:</p><ul>'
    body+=''.join('<li>'+html.escape(item)+'</li>' for item in PENDING)+'</ul>'
    write(SHARED/'Acceptance.html',body)
def verify_only():
    health(scoring=True); data=checks()
    assert not any(data.values()),'Starting-image check earned unexpected credit'
    html=(ROOT/'assets/ScoringReport.html').read_text()
    assert re.search(r'0 out of 100 points received',html),'Production report is not 0/100'
    public_status(True,'Post-boot runtime and starting-state scoring checked; manual acceptance remains pending.')
    write(BACKUP/'boot-verified.json',json.dumps({'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'starting_score':0,'manual_acceptance_pending':PENDING},indent=2),0o600)
    print('Starting state 0/100; production runtime available. Manual acceptance remains pending.')
def rpm_state(name):
    out=call(['rpm','-q','--qf','%{NEVRA}',name],ok=(0,1))
    return None if out=='package %s is not installed'%name else out
class Packages:
    def __init__(self):
        directory=pathlib.Path('/var/backups/summit-package-recovery-retry1')
        inventory=json.loads((directory/'inventory.json').read_text()); assert inventory['installed_package_set_unchanged'] is True
        entries=inventory['rpms']; self.entries=entries; self.files={}
        for item in entries:
            path=safe_path(item['file']); assert path.is_file() and directory in path.parents
            assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],'Recovery RPM hash mismatch'
            assert 'signatures OK' in call(['rpm','--checksig',path]),'Recovery RPM signature invalid'
            name=call(['rpm','-qp','--qf','%{NAME}',path]); self.files[name]=path
        assert {'nmap','cockpit','cockpit-ws','dnf-automatic'}<=self.files.keys()
    def install(self,names):
        call(['dnf','-y','--disablerepo=*','--setopt=gpgcheck=1','--setopt=localpkg_gpgcheck=1',
              '--setopt=keepcache=1','install']+[self.files[n] for n in names],timeout=180)
        for item in self.entries:
            assert hashlib.sha256(pathlib.Path(item['file']).read_bytes()).hexdigest()==item['sha256'],'Recovery RPM changed'
    def restore(self,before):
        missing=[n for n,version in before.items() if version is not None and rpm_state(n)!=version]
        if missing: self.install(missing)
        extra=[n for n,version in before.items() if version is None and rpm_state(n) is not None]
        if extra: call(['rpm','-e','--test']+extra); call(['rpm','-e']+extra)
        assert {n:rpm_state(n) for n in before}==before,'Package recovery differs from original'
class Snapshot:
    def __init__(self,path,targets,packages):
        self.path=path; self.path.mkdir(mode=0o700); self.entries=[]; self.packages=packages
        self.rpms={n:rpm_state(n) for n in packages.files}; self.units=states()
        self.zone=call(['firewall-cmd','--get-zone-of-interface=ens160'])
        connection=call(['nmcli','-g','GENERAL.CONNECTION','device','show','ens160'])
        self.uuid=call(['nmcli','-g','connection.uuid','connection','show',connection])
        assert re.fullmatch(r'[0-9a-f-]{36}',self.uuid),'Unexpected NetworkManager connection'
        self.nm_zone=call(['nmcli','-g','connection.zone','connection','show',self.uuid])
        self.selinux=call(['getenforce']); self.tmp_mode=pathlib.Path('/tmp').stat().st_mode & 0o7777
        self.audit=call(['auditctl','-l']); self.identity={}
        for name in ('passwd','shadow','group','gshadow'):
            self.identity[name]=pathlib.Path('/etc/'+name).read_bytes()
        for index,value in enumerate(targets):
            target=safe_path(value,allow_leaf_symlink=True); saved=self.path/str(index)
            exists=target.exists() or target.is_symlink()
            metadata_only=target==SHARED/'Downloads' or target.name in ('Documents','Downloads') and any(target==pathlib.Path(pwd.getpwnam(u).pw_dir)/target.name for u in scenario.CONTENT_USERS)
            self.entries.append((target,saved,exists,metadata_only))
            if exists:
                if metadata_only:
                    saved.mkdir()
                    call(['chown','--reference='+str(target),saved]); call(['chmod','--reference='+str(target),saved])
                    call(['setfacl','--set-file=-',saved],input=call(['getfacl','-cp',target])+'\n')
                    call(['chcon','--reference='+str(target),saved])
                else: call(['cp','-a',target,saved])
        (self.path/'index.json').write_text(json.dumps({'entries':[{'target':str(p),'saved':str(q),'existed':e,'metadata_only':m} for p,q,e,m in self.entries],
            'rpm_state':self.rpms,'unit_states':self.units,'zone':self.zone,'nm_uuid':self.uuid,
            'nm_zone':self.nm_zone,'selinux':self.selinux,'tmp_mode':self.tmp_mode,'audit_rules':self.audit},indent=2))
        (self.path/'index.json').chmod(0o600)
    @classmethod
    def from_record(cls,path,targets,packages):
        path=safe_path(path)
        assert path.is_dir() and path.stat().st_uid==0 and path.stat().st_mode & 0o077==0,'Unsafe saved snapshot directory'
        source=safe_path(path/'index.json')
        assert source.stat().st_uid==0 and source.stat().st_mode & 0o077==0,'Unsafe snapshot index'
        index=json.loads(source.read_text()); instance=cls.__new__(cls)
        instance.path=path; instance.packages=packages
        instance.entries=validated_snapshot_entries(path,index,targets)
        instance.rpms=index['rpm_state']; instance.units=index['unit_states']
        assert set(instance.rpms)==set(packages.files) and set(instance.units)==set(UNITS),'Incomplete saved state'
        instance.zone=index['zone']; instance.uuid=index['nm_uuid']; instance.nm_zone=index['nm_zone']
        assert valid_zone_name(instance.zone) and re.fullmatch(r'[0-9a-f-]{36}',instance.uuid),'Invalid saved network state'
        instance.selinux=index['selinux']; instance.tmp_mode=index['tmp_mode']; instance.audit=index['audit_rules']
        assert instance.selinux in ('Enforcing','Permissive') and type(instance.tmp_mode) is int and 0<=instance.tmp_mode<=0o7777,'Invalid saved protections'
        instance.identity={target.name:saved.read_bytes() for target,saved,exists,_ in instance.entries if target.parent==pathlib.Path('/etc') and target.name in ('passwd','shadow','group','gshadow') and exists}
        assert len(instance.identity)==4,'Saved identity recovery files are incomplete'
        return instance

    def restore(self):
        call(['systemctl','stop','summit-aeacus.service'])
        current_units=states()
        for unit,state in self.units.items():
            if state.get('LoadState')!='loaded' and current_units[unit].get('LoadState')=='loaded':
                call(['systemctl','disable','--now',unit],ok=(0,1,5))
        for unit in ('summit-marker.timer','summit-marker.service',AUTO_TIMER,'avahi-daemon.socket','cups.socket','cups.path'):
            call(['systemctl','stop',unit],ok=(0,1,5))
        self.packages.restore(self.rpms)
        restore_identity(self.identity)
        for target,saved,exists,metadata_only in reversed(self.entries):
            if target.parent==pathlib.Path('/etc') and target.name in self.identity:
                continue
            restored=restore_entry(target,saved,exists,metadata_only,call,('/opt/aeacus/probes','/opt/aeacus/helpers'))
            if not restored: print('Preserved newly populated competitor directory: '+str(target),flush=True)
        pathlib.Path('/tmp').chmod(self.tmp_mode)
        call(['nmcli','connection','modify',self.uuid,'connection.zone',self.nm_zone])
        call(['firewall-cmd','--reload']); call(['firewall-cmd','--zone='+self.zone,'--change-interface=ens160'])
        call(['setenforce','1' if self.selinux=='Enforcing' else '0'])
        # Remove only the exact five scenario watches, preserving other live rules.
        now=call(['auditctl','-l'])
        for path in WATCHES:
            if any('-w '+path+' ' in line and 'summit-identity' in line for line in now.splitlines()) and not any('-w '+path+' ' in line and 'summit-identity' in line for line in self.audit.splitlines()):
                call(['auditctl','-W',path,'-p','wa','-k','summit-identity'])
        call(['dconf','update']); call(['update-ca-trust','extract']); call(['systemctl','daemon-reload'])
        call(['systemctl','restart','systemd-journald'])
        for unit,state in self.units.items():
            if state.get('LoadState')!='loaded' or unit in ('auditd.service','summit-marker.service','summit-marker.timer'): continue
            enable=state.get('UnitFileState')
            if enable in ('enabled','disabled'): call(['systemctl','enable' if enable=='enabled' else 'disable',unit])
            call(['systemctl','start' if state.get('ActiveState')=='active' else 'stop',unit],ok=(0,5))
        marker=self.units['summit-marker.service']; timer=self.units['summit-marker.timer']
        if marker.get('LoadState')=='loaded':
            # A timer-driven oneshot is momentarily active; restore healthy execution,
            # then enable its timer last, never start a timer before stopping its job.
            ensure_marker_ready(force=True)
        if timer.get('LoadState')=='loaded':
            enable=timer.get('UnitFileState')
            if enable in ('enabled','disabled'): call(['systemctl','enable' if enable=='enabled' else 'disable','summit-marker.timer'])
            call(['systemctl','start' if timer.get('ActiveState')=='active' else 'stop','summit-marker.timer'])
        call(['restorecon','/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow','/tmp'])
        health()
def restore_identity(original,directory=pathlib.Path('/etc')):
    """Serialize with PAM/shadow-utils, then atomically replace merged files."""
    import ctypes,tempfile
    libc=ctypes.CDLL(None,use_errno=True); locks=[]
    assert libc.lckpwdf()==0,'Cannot acquire account-database lock; recovery retained'
    try:
        for name in ('passwd','shadow','group','gshadow'):
            lock=directory/(name+'.lock')
            fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
            locks.append(lock)
            with os.fdopen(fd,'w') as output: output.write(str(os.getpid())+'\n')
        for name,old in original.items():
            target=safe_path(directory/name)
            merged=restore_training_identity(old,target.read_bytes(),name)
            fd,filename=tempfile.mkstemp(prefix='.summit-identity-',dir=directory); os.close(fd)
            temporary=pathlib.Path(filename)
            try:
                call(['cp','-a',target,temporary])
                with temporary.open('wb') as output:
                    output.write(merged); output.flush(); os.fsync(output.fileno())
                os.replace(temporary,target)
            finally:
                if temporary.exists(): temporary.unlink()
        if hasattr(os,'O_DIRECTORY'):
            descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    finally:
        for lock in reversed(locks): lock.unlink()
        libc.ulckpwdf()

def target_paths():
    paths=['/opt/aeacus','/opt/aeacus/probes','/opt/aeacus/helpers','/opt/aeacus/finish_runtime.py','/opt/aeacus/manifest.json','/opt/aeacus/scoring.conf','/opt/aeacus/ReadMe.conf',
           '/etc/firewalld','/etc/firewalld/zones/'+ZONE+'.xml','/etc/selinux/config','/etc/audit/audit.rules',str(AUDIT),str(AUTO),str(AUTO)+'.rpmsave',str(AUTO)+'.rpmnew',str(TIMER_DROP.parent),str(TIMER_DROP),
           '/etc/security/pwquality.conf','/etc/security/pwhistory.conf','/etc/security/faillock.conf',
           '/etc/ssh/sshd_config','/etc/sudoers.d/90-summit-training-auditor','/etc/sudoers.d/94-summit-domain-scenario',
           '/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow','/etc/firefox/policies/policies.json','/etc/dnf/dnf.conf',
           '/etc/summit-workstation/app.conf','/etc/profile.d/summit-workstation.sh',
           '/etc/dconf/db/local.d/90-summit-screenlock','/etc/dconf/db/local.d/locks/summit-screenlock',
           '/etc/systemd/journald.conf.d/zz-summit-training.conf',
           '/etc/pki/ca-trust/source/anchors/summit-fictional-training.crt',
           '/home/summit-keyuser/.ssh','/etc/cron.d/summit-marker',
           '/etc/systemd/system/summit-marker.timer','/etc/systemd/system/summit-marker.service',
           '/usr/local/lib/summit-training/cron-marker.sh','/usr/local/lib/summit-training/systemd-marker.sh',
           '/usr/local/share/summit-games/offline-game.py','/etc/systemd/system/summit-aeacus.service',
           '/etc/systemd/system/summit-image-verify.service',str(SHARED/'Downloads'),str(SHARED/'Instructions.html'),
           str(SHARED/'ScoringReport.html'),str(SHARED/'Acceptance.html')]
    paths+=list(scenario.FORENSICS_FILES.values())
    paths+=[str(SHARED/'Downloads'/name) for name in ('summit-fictional-credentials.txt','summit-personal-media.zip')]
    paths+=['/home/jwang/Downloads/summit-fictional-credentials.txt','/home/jwang/Downloads/summit-personal-media.zip','/home/jwang/Desktop/summit-offline-game.desktop']
    for user in scenario.CONTENT_USERS:
        home=pathlib.Path(pwd.getpwnam(user).pw_dir)
        paths+=[str(home/name) for name in ('Documents','Downloads')]
        paths+=[str(home/'Desktop'/name) for name in ('Summit-Files.desktop','summit-offline-game.desktop','Summit-Report.desktop')]
    return list(dict.fromkeys(paths))
def firewall(protected,uuid):
    call(['nmcli','connection','modify',uuid,'connection.zone',ZONE])
    for permanent in (True,False):
        prefix=['firewall-cmd']+(['--permanent'] if permanent else [])+['--zone='+ZONE]
        call(prefix+['--change-interface=ens160'])
        for proto in ('tcp','udp'):
            call(prefix+[('--remove-port=' if protected else '--add-port=')+'1-65535/'+proto])
    if protected: assert access.check(15),'Restrictive firewall probe failed'
    else: assert not access.check(15),'Broad ports falsely scored'
def selinux(protected):
    path=pathlib.Path('/etc/selinux/config'); text=path.read_text()
    text,count=re.subn(r'^SELINUX=\w+[ \t]*$', 'SELINUX='+('enforcing' if protected else 'permissive'),text,flags=re.M)
    assert count==1,'Unexpected SELinux configuration'; write(path,text)
    call(['setenforce','1' if protected else '0'])
def audit(protected):
    if protected:
        write(AUDIT,''.join('-w '+path+' -p wa -k summit-identity\n' for path in WATCHES))
        for path in WATCHES: call(['auditctl','-w',path,'-p','wa','-k','summit-identity'])
    else:
        if AUDIT.exists(): AUDIT.unlink()
        live=call(['auditctl','-l'])
        for path in WATCHES:
            if any('-w '+path+' ' in line and 'summit-identity' in line for line in live.splitlines()):
                call(['auditctl','-W',path,'-p','wa','-k','summit-identity'])
    call(['augenrules'])  # Compile boot rules; do not wipe unrelated live rules.
def automatic(protected):
    cfg=configparser.ConfigParser(interpolation=None); cfg.read(AUTO)
    if not cfg.has_section('commands'): cfg.add_section('commands')
    for key,value in {'upgrade_type':'security','download_updates':'yes','apply_updates':'yes' if protected else 'no'}.items(): cfg.set('commands',key,value)
    import io
    output=io.StringIO(); cfg.write(output); write(AUTO,output.getvalue())
    call(['systemctl','daemon-reload']); call(['systemctl','enable' if protected else 'disable','--now',AUTO_TIMER])
    if protected:
        due=call(['systemctl','show',AUTO_TIMER,'-p','NextElapseUSecRealtime','--value'])
        assert due not in ('','n/a'),'Security update timer has no next scheduled run'
        next_run=call(['date','--date='+due,'+%s'])
        assert int(next_run)>time.time()+3600,'Update timer may fire during rehearsal'
def engine_score(resources,label,expected):
    folder=BACKUP/('engine-'+label); folder.mkdir(mode=0o700)
    call(['cp','-a',ROOT/'assets',folder/'assets'])
    conf=(resources/'probe-validation-scoring.conf').read_text().replace('/home/jwang/aeacus-setup/probes/',str(resources/'probes')+'/')
    if label=='solution':
        conf=conf.replace('/usr/bin/python3 '+str(resources/'probes'/'scenario.py'),'/usr/bin/env SUMMIT_FORENSICS_ROOT='+str(BACKUP/'solution-questions')+' /usr/bin/python3 '+str(resources/'probes'/'scenario.py'))
    write(folder/'scoring.conf',conf,0o600)
    write(folder/'TeamID.txt','ORGANIZER-REHEARSAL\n',0o600)
    log=call([ROOT/'aeacus','--dir',str(folder)+'/', '--verbose','check'],timeout=180,cwd=folder)
    log+='\n'+call([ROOT/'aeacus','--dir',str(folder)+'/', '--verbose','score'],timeout=180,cwd=folder)
    write(folder/'engine.log',log,0o600)
    html=(folder/'assets/ScoringReport.html').read_text()
    actual=re.search(r'(\d+) out of (\d+) points received',html)
    assert actual and tuple(map(int,actual.groups()))==(expected,100),label+' engine score differs'
    print(label+': '+str(expected)+'/100',flush=True)
def migrate_content():
    group=int(call(['getent','group','linux-workstation-admins@corp.summit.test']).split(':')[2])
    directory=SHARED/'Downloads'; directory.mkdir(mode=0o2775); directory.chmod(0o2775); os.chown(directory,0,group)
    fallback=pwd.getpwnam('competitor-recovery')
    call(['setfacl','-m','u:%d:rwx'%fallback.pw_uid,directory])
    hashes=json.loads((RES/'artifact-hashes.json').read_text())
    for source,name,key in (('/home/jwang/Downloads/summit-fictional-credentials.txt','summit-fictional-credentials.txt','fictional-credentials.txt'),('/home/jwang/Downloads/summit-personal-media.zip','summit-personal-media.zip','personal-media.zip')):
        src=safe_path(source); assert hashlib.sha256(src.read_bytes()).hexdigest()==hashes[key],'Planted artifact changed'
        dest=directory/name; call(['cp','-a',src,dest]); os.chown(dest,0,group); dest.chmod(0o664); src.unlink()
    old=pathlib.Path('/home/jwang/Desktop/summit-offline-game.desktop')
    assert hashlib.sha256(old.read_bytes()).hexdigest()==hashes['summit-offline-game.desktop']; old.unlink()
    for user in scenario.CONTENT_USERS:
        identity=pwd.getpwnam(user); home=pathlib.Path(identity.pw_dir)
        for name in ('Documents','Downloads'):
            path=safe_path(home/name)
            if not path.exists(): path.mkdir(mode=0o700); os.chown(path,identity.pw_uid,identity.pw_gid)
        if user not in USERS: continue
        for filename,title,command in (('Summit-Files.desktop','Summit Shared Files','nautilus /srv/summit-competition/Downloads'),('summit-offline-game.desktop','Summit Offline Game','python3 /usr/local/share/summit-games/offline-game.py')):
            path=home/'Desktop'/filename; assert not path.exists()
            write(path,'[Desktop Entry]\nType=Application\nName='+title+'\nExec='+command+'\nTerminal=false\n',0o755)
            os.chown(path,identity.pw_uid,identity.pw_gid)
        call(['runuser','-u',user,'--','test','-r',directory/'summit-fictional-credentials.txt'])
        call(['runuser','-u',user,'--','test','-w',directory])
    call(['restorecon','-R',directory])
def full_repair(uuid):
    quality={'minlen':'14','enforcing':'1','dcredit':'0','ucredit':'0','lcredit':'0','ocredit':'0','dictcheck':'1','usercheck':'1','local_users_only':None}
    for name,values in (('pwquality',quality),('pwhistory',{'remember':'5'}),('faillock',{'deny':'5','fail_interval':'900','unlock_time':'900','local_users_only':None})):
        path=pathlib.Path('/etc/security/'+name+'.conf'); write(path,update_policy(path.read_text(),values))
    ssh=pathlib.Path('/etc/ssh/sshd_config'); write(ssh,ssh_repair(ssh.read_text()),0o600); call(['/usr/sbin/sshd','-t'])
    # Candidate policy is inspected by sshd -T; the live SSH daemon keeps access.
    key=pathlib.Path('/home/summit-keyuser/.ssh'); key.chmod(0o700); (key/'authorized_keys').chmod(0o600)
    browser=pathlib.Path('/etc/firefox/policies/policies.json'); write(browser,json.dumps(firefox_state(json.loads(browser.read_text()),True),indent=2)+'\n')
    anchor=pathlib.Path('/etc/pki/ca-trust/source/anchors/summit-fictional-training.crt')
    before=trust.current_fingerprints()
    assert before and trust.TRAINING_CA_SHA256 in before,'Fictional CA baseline differs'
    assert trust.certificate_fingerprints(anchor.read_text())=={trust.TRAINING_CA_SHA256},'Anchor content differs; refusing removal'
    anchor.unlink(); call(['update-ca-trust','extract'])
    assert trust.current_fingerprints()==before-{trust.TRAINING_CA_SHA256},'Unrelated trust anchors changed'
    for path in ('/etc/summit-workstation/app.conf','/etc/profile.d/summit-workstation.sh'): pathlib.Path(path).chmod(0o644)
    call(['cp','-a','/var/backups/summit-application-stage/dnf.conf','/etc/dnf/dnf.conf'])
    firewall(True,uuid); selinux(True)
    private=BACKUP/'solution-questions'; private.mkdir(mode=0o700)
    for issue,(number,value) in scenario.ANSWERS.items():
        path=pathlib.Path(scenario.FORENSICS_FILES[issue]); text=path.read_text()
        destination=private/path.name
        write(destination,re.sub(r'^Answer[ \t]*=.*$',lambda match:'Answer = '+value,text,flags=re.M),0o600)
        scenario.FORENSICS_FILES[issue]=str(destination)
    pathlib.Path('/etc/sudoers.d/94-summit-domain-scenario').unlink(); call(['visudo','-c'])
    audit(True)
    write('/etc/systemd/journald.conf.d/zz-summit-training.conf','[Journal]\nStorage=persistent\n')
    pathlib.Path('/var/log/journal').mkdir(exist_ok=True); call(['systemd-tmpfiles','--create','--prefix=/var/log/journal'])
    call(['systemctl','restart','systemd-journald']); call(['journalctl','--flush'])
    call(['systemctl','disable','--now','summit-marker.timer']); call(['systemctl','stop','summit-marker.service'])
    for path in ('/etc/cron.d/summit-marker','/etc/systemd/system/summit-marker.timer','/etc/systemd/system/summit-marker.service','/usr/local/lib/summit-training/cron-marker.sh','/usr/local/lib/summit-training/systemd-marker.sh'):
        pathlib.Path(path).unlink()
    call(['systemctl','daemon-reload'])
    automatic(True)
    for path in (SHARED/'Downloads/summit-fictional-credentials.txt',SHARED/'Downloads/summit-personal-media.zip',pathlib.Path('/usr/local/share/summit-games/offline-game.py')): path.unlink()
    for user in USERS: (pathlib.Path(pwd.getpwnam(user).pw_dir)/'Desktop/summit-offline-game.desktop').unlink()
    call(['systemctl','disable','--now','avahi-daemon.service','avahi-daemon.socket','cups.service','cups.socket','cups.path'])
    write('/etc/dconf/db/local.d/90-summit-screenlock','[org/gnome/desktop/screensaver]\nlock-enabled=true\nlock-delay=uint32 0\n[org/gnome/desktop/session]\nidle-delay=uint32 300\n'); call(['dconf','update'])
    pathlib.Path('/tmp').chmod(0o1777)
    call(['systemctl','disable','--now','cockpit.socket']); call(['systemctl','stop','cockpit.service'])
    call(['rpm','-e','--test','cockpit','cockpit-ws','nmap']); call(['rpm','-e','cockpit','cockpit-ws','nmap']); call(['systemctl','daemon-reload'])
    for user in ('summit-unknown','summit-departed'):
        call(['passwd','--lock',user]); call(['usermod','--expiredate','1970-01-02','--shell','/sbin/nologin',user])
    call(['gpasswd','--delete','summit-employee','wheel']); pathlib.Path('/etc/sudoers.d/90-summit-training-auditor').unlink(); call(['visudo','-c'])
    # Repository/security preview only: never apply arbitrary upgrades mid-build.
    import dnf
    base=dnf.Base(); base.read_all_repos(); enabled=list(base.repos.iter_enabled())
    assert enabled and {r.id.lower() for r in enabled}<= {'baseos','appstream','extras'} and all(r.gpgcheck for r in enabled),'Unexpected/unsigned enabled repositories'
    preview=call(['dnf','-q','--security','check-update'],ok=(0,100),timeout=240)
    write(BACKUP/'security-update-preview.txt',preview+'\n',0o600)
    health()
def engine_compatibility():
    """Exercise the real encrypted engine in private storage before any mutations."""
    directory=RES/'engine-compatibility'; directory.mkdir(mode=0o700)
    call(['cp','-a',ROOT/'assets',directory/'assets'])
    write(directory/'assets/previous.txt','0',0o600)
    config=(RES/'probe-validation-scoring.conf').read_text()
    config=re.sub(r'^cmd = .*$', 'cmd = "/usr/bin/printf FAIL"',config,flags=re.M)
    config=config.replace('user = "alex.admin@corp.summit.test"','user = "jwang"')
    write(directory/'scoring.conf',config,0o600)
    write(directory/'ReadMe.conf','<h1>Organizer-only engine compatibility test</h1>',0o600)
    write(directory/'TeamID.txt','ORGANIZER-COMPATIBILITY\n',0o600)
    for action in ('check','readme','score','encrypt'):
        log=call([ROOT/'aeacus','--dir',str(directory)+'/', '--verbose',action],timeout=180,cwd=directory)
        write(directory/(action+'.log'),log,0o600)
    assert (directory/'scoring.dat').stat().st_size>0,'Isolated encryption produced no data'
    (directory/'scoring.dat').chmod(0o600); (directory/'scoring.conf').unlink()
    private_phocus(directory,ROOT/'phocus')
    assert '0 out of 100 points received' in (directory/'assets/ScoringReport.html').read_text(),'Encrypted compatibility score differs'
    assert 'Organizer-only engine compatibility test' in (directory/'assets/ReadMe.html').read_text(),'Isolated README generation differs'
    print('Actual Aeacus README, 40-check encryption and encrypted scoring passed in private storage; system configuration unchanged.',flush=True)

def install_runtime():
    for directory in (ROOT/'probes',ROOT/'helpers'):
        directory.mkdir(mode=0o700); directory.chmod(0o700)
    for source in (RES/'probes').glob('*.py'):
        if not source.name.startswith('test_'): call(['install','-o','root','-g','root','-m','700',source,ROOT/'probes'/source.name])
    for name in ('auth_policy.py','application_stage.py','finish_helpers.py'):
        call(['install','-o','root','-g','root','-m','700',RES/name,ROOT/'helpers'/name])
    call(['install','-o','root','-g','root','-m','700',RES/'finish_workstation.py',ROOT/'finish_runtime.py'])
    call(['install','-o','root','-g','root','-m','600',RES/'competition-manifest.json',ROOT/'manifest.json'])
    write(ROOT/'helpers/finish-backup.json',json.dumps({'path':str(BACKUP)}),0o600)
    conf=(RES/'probe-validation-scoring.conf').read_text().replace('/home/jwang/aeacus-setup/probes/','/opt/aeacus/probes/')
    conf=conf.replace('summit-workstation01-probe-validation','summit-workstation01-competition').replace('Organizer Probe Validation - Not Competition Scoring','Summit Supply - AlmaLinux Workstation')
    write(BACKUP/'competition-master.conf',conf,0o600); write(ROOT/'scoring.conf',conf,0o600)
    instructions=(RES/'competition-ReadMe.conf').read_text()
    instructions=re.sub(r'<p><strong>Draft participant instructions\.</strong>.*?</p>','',instructions,flags=re.S)
    write(ROOT/'ReadMe.conf',instructions,0o600); write(SHARED/'Instructions.html',instructions)
    write(ROOT/'TeamID.txt','SUMMIT-WORKSTATION01-PRACTICE\n')
    for action in ('check','readme','score','encrypt'):
        log=call([ROOT/'aeacus','--dir',str(ROOT)+'/', '--verbose',action],timeout=180,cwd=ROOT)
        write(BACKUP/('production-'+action+'.log'),log,0o600)
    assert (ROOT/'scoring.dat').stat().st_size>0; (ROOT/'scoring.dat').chmod(0o600); (ROOT/'scoring.conf').unlink()
    (SHARED/'ScoringReport.html').unlink(); (SHARED/'ScoringReport.html').symlink_to(ROOT/'assets/ScoringReport.html')
    (ROOT/'assets/ScoringReport.html').chmod(0o644); (ROOT/'assets/ReadMe.html').chmod(0o644)
    write('/etc/systemd/system/summit-image-verify.service','[Unit]\nDescription=Summit read-only image acceptance check\nConditionPathExists=!/var/backups/summit-workstation01-finish/boot-verified.json\nWants=network-online.target\nAfter=network-online.target summit-aeacus.service sssd.service firewalld.service\n[Service]\nType=oneshot\nUser=root\nExecStart=/usr/bin/python3 /opt/aeacus/finish_runtime.py --verify-only\n[Install]\nWantedBy=multi-user.target\n'.replace('/var/backups/summit-workstation01-finish/boot-verified.json',str(BACKUP/'boot-verified.json')))
    for user in USERS:
        identity=pwd.getpwnam(user); desktop=pathlib.Path(identity.pw_dir)/'Desktop'
        report=desktop/'Summit-Report.desktop'; report.write_text(report.read_text().replace('Summit Practice Validation Report','Summit Scoring Report'))
        for path in desktop.glob('*desktop'):
            subprocess.run(['runuser','-u',user,'--','gio','set',str(path),'metadata::trusted','true'],capture_output=True,timeout=15)
    call(['restorecon','-R',ROOT]); call(['systemctl','daemon-reload'])
    call(['systemctl','enable','summit-image-verify.service','summit-aeacus.service'])
    (ROOT/'assets/ScoringReport.html').unlink()
    call(['systemctl','restart','summit-aeacus.service'])
    wait_scoring_report(ROOT/'assets/ScoringReport.html',lambda:call(['systemctl','is-active','summit-aeacus.service'],ok=(0,3))=='active')
    (ROOT/'assets/ScoringReport.html').chmod(0o644)
    health(scoring=True)
    assert re.search(r'0 out of 100 points received',(ROOT/'assets/ScoringReport.html').read_text()),'Production score differs'
    public_status(True,'40-check scoring configured after 100/100 solution and 0/100 restoration rehearsals. Manual acceptance pending.')
def ensure_marker_ready(force=False):
    properties=('Type','User','Group','NoNewPrivileges','ProtectSystem','ProtectHome','PrivateTmp','DropInPaths','ExecStart','Result','ExecMainStatus','ExecMainCode','ActiveState')
    args=['systemctl','show','summit-marker.service']
    for key in properties: args+=['-p',key]
    info=dict(line.split('=',1) for line in call(args).splitlines() if '=' in line)
    if not force and info.get('ActiveState')!='failed': return
    if not force:
        assert info.get('Result')=='signal' and info.get('ExecMainStatus')=='15' and info.get('ExecMainCode')=='2','Marker has an unexplained execution failure'
    required={'Type':'oneshot','User':'summit-marker-runner','Group':'summit-marker-runner','NoNewPrivileges':'yes','ProtectSystem':'strict','ProtectHome':'yes','PrivateTmp':'yes','DropInPaths':''}
    assert all(info.get(k)==v for k,v in required.items()),'Marker sandbox differs; refusing execution'
    script=safe_path('/usr/local/lib/summit-training/systemd-marker.sh')
    hashes=json.loads((RES/'artifact-hashes.json').read_text())
    assert hashlib.sha256(script.read_bytes()).hexdigest()==hashes['systemd-marker.sh'],'Marker payload changed; refusing execution'
    exec_start=info.get('ExecStart','')
    assert re.findall(r'path=([^ ;]+)',exec_start)==[str(script)] and re.findall(r'argv\[\]=(.*?) ;',exec_start)==[str(script)],'Marker command differs; refusing execution'
    timer=states()['summit-marker.timer']
    resume=timer.get('ActiveState')=='active'
    call(['systemctl','stop','summit-marker.timer'])
    try:
        call(['systemctl','stop','summit-marker.service'])
        stopped=dict(line.split('=',1) for line in call(args).splitlines() if '=' in line)
        if stopped.get('ActiveState')=='failed':
            call(['systemctl','reset-failed','summit-marker.service'])
        call(['systemctl','start','summit-marker.service'])
        result=dict(line.split('=',1) for line in call(args).splitlines() if '=' in line)
        assert result.get('Result')=='success' and result.get('ExecMainStatus')=='0' and result.get('ActiveState')=='inactive','Inert marker did not complete successfully'
        print('Pinned, unprivileged marker completed successfully; restoring its timer last.',flush=True)
    finally:
        if resume: call(['systemctl','start','summit-marker.timer'])

def recover_interrupted_attempts(base,packages):
    for number in range(100):
        record=base if number==0 else base.with_name(base.name+'-retry'+str(number))
        record=safe_path(record)
        if not record.exists(): return
        assert record.is_dir() and record.stat().st_uid==0 and record.stat().st_mode & 0o077==0,'Unsafe recovery records'
        if (record/'completed.json').exists(): raise RuntimeError('Image already completed; refusing new staging')
        error=record/'rollback-failure.txt'
        if not error.exists() or verified_receipt(record/'recovery-verified.json'): continue
        known='Failed to reset failed state of unit summit-marker.service: Unit summit-marker.service not loaded.'
        assert known in error.read_text(),'Unrecognized rollback failure; recovery records retained'
        print('Recovering the saved pre-script state from '+str(record)+' before any new finish attempt.',flush=True)
        snapshot=Snapshot.from_record(record/'initial',target_paths(),packages)
        snapshot.restore()
        health(scoring=True)
        assert checks()=={i:i in (16,32) for i in range(1,41)},'Recovered probe state differs from 6/100'
        verify_previous_attempts([record],packages)
        write(record/'recovery-verified.json',json.dumps({'verified':True,'score':6,'original_rollback_failure_retained':True}),0o600)
        print('Pre-script recovery verified at 6/100; original failure records retained.',flush=True)
    raise RuntimeError('Too many prior attempts')

def verify_previous_attempts(records,packages):
    for record in records:
        assert record.stat().st_uid==0 and record.stat().st_mode & 0o077==0,'Unsafe prior recovery directory'
        index=json.loads((record/'initial/index.json').read_text())
        assert {n:rpm_state(n) for n in packages.files}==index['rpm_state'],'Previous package rollback differs'
        assert call(['getenforce'])==index['selinux'],'Previous SELinux rollback differs'
        assert pathlib.Path('/tmp').stat().st_mode & 0o7777==index['tmp_mode'],'Previous temporary-directory rollback differs'
        assert call(['nmcli','-g','connection.zone','connection','show',index['nm_uuid']])==index['nm_zone'],'Previous NM rollback differs'
        assert call(['firewall-cmd','--get-zone-of-interface=ens160'])==index['zone'],'Previous firewall binding differs'
        ensure_marker_ready()
        current=states()
        for unit,old in index['unit_states'].items():
            assert unit_state_matches(unit,current[unit],old),'Previous unit rollback differs: '+unit+' '+json.dumps(current[unit])
        # The known first failure occurs before firewall/identity/content changes.
        # Restored files already covered by the live 6/100 probes remain checked above.
        assert not TIMER_DROP.exists(),'Previous timer drop-in remains'
        assert not pathlib.Path('/etc/firewalld/zones/summit-workstation.xml').exists(),'Legacy zone unexpectedly exists'
        print('Verified previous rollback; retaining records in '+str(record),flush=True)

def main():
    global BACKUP
    print('Checking pinned machine, required services, recovery packages and current 40-check state.',flush=True)
    assert os.geteuid()==0 and call(['hostname','-s'])=='workstation01','Wrong machine or privilege'
    assert 'VERSION_ID="9.8"' in pathlib.Path('/etc/os-release').read_text(),'Unexpected OS version'
    fingerprint=call(['ssh-keygen','-lf','/etc/ssh/ssh_host_ed25519_key.pub'])
    assert 'SHA256:26ZBMONpdd0dFMo0SwS+P2xPT2lbkDHjKaTxYeuFSAw' in fingerprint,'Machine host key differs'
    assert valid_zone_name(ZONE),'Invalid firewall zone name; no finishing mutations made'
    engine_compatibility()
    packages=Packages()
    recover_interrupted_attempts(BACKUP,packages)
    next_backup,previous=choose_finish_backup(BACKUP)
    health(scoring=True)
    profile=call(['authselect','current','-r']).split()
    assert profile[0]=='sssd' and set(profile[1:])=={'with-mkhomedir','with-pwhistory','with-faillock'},'Password-policy batch not completed'
    assert checks()=={i:i in (16,32) for i in range(1,41)},'Starting probes differ from expected 6/100; no finishing mutations made'
    assert re.search(r'^enabled\s+1$',call(['auditctl','-s']),re.M),'Audit rules are immutable/disabled; need inspection before changes'
    assert not AUDIT.exists() and 'summit-identity' not in call(['auditctl','-l']),'Existing scenario watches would be overwritten'
    assert not pathlib.Path('/etc/firewalld/zones/'+ZONE+'.xml').exists(),'Scenario firewall zone already exists'
    for permanent in (False,True):
        prefix=['firewall-cmd']+(['--permanent'] if permanent else [])
        assert not call(prefix+['--direct','--get-all-rules']),'Unexpected direct firewall rules'
        assert set(call(prefix+['--get-policies']).split())<= {'allow-host-ipv6'},'Custom firewall policies need review'
        for zone in call(prefix+['--get-zones']).split():
            assert not call(prefix+['--zone='+zone,'--list-sources']),'Source-bound firewall zones need review'
            assert set(call(prefix+['--zone='+zone,'--list-interfaces']).split())<= {'ens160','lo'},'Additional interface zones need review'
    active=call(['firewall-cmd','--get-active-zones'])
    assert all('sources:' not in line or not line.split(':',1)[1].strip() for line in active.splitlines()),'Source-bound firewall zones need review'
    assert not TIMER_DROP.exists() and not (SHARED/'Downloads').exists(),'Finishing paths already exist'
    verify_previous_attempts(previous,packages)
    BACKUP=next_backup; BACKUP.mkdir(mode=0o700); targets=target_paths()
    initial=Snapshot(BACKUP/'initial',targets,packages); starting=None
    try:
        call(['systemctl','stop','summit-aeacus.service'])
        packages.install(['dnf-automatic'])
        # Schedule repaired updates twelve hours ahead; no missed-run catchup.
        schedule=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=12)
        write(TIMER_DROP,'[Timer]\nOnBootSec=\nOnUnitActiveSec=\nOnCalendar=\nOnCalendar=*-*-* '+schedule.strftime('%H:%M:00')+' UTC\nPersistent=false\nRandomizedDelaySec=0\n')
        call(['firewall-cmd','--permanent','--new-zone='+ZONE]); call(['firewall-cmd','--permanent','--zone='+ZONE,'--add-service=ssh'])
        call(['firewall-cmd','--permanent','--zone='+ZONE,'--add-service=dhcpv6-client']); call(['firewall-cmd','--reload'])
        for index,protected in enumerate((True,False,True,False),1):
            print('Remaining-control rehearsal '+str(index)+'/4: '+('protected' if protected else 'weak')+' state.',flush=True)
            firewall(protected,initial.uuid); selinux(protected); audit(protected); automatic(protected)
            pathlib.Path('/tmp').chmod(0o1777 if protected else 0o777)
            data=checks()
            assert all(data[i]==protected for i in (15,16,22,26,32)),'Remaining-control rehearsal failed'
            health()
        print('Preparing shared competitor content and starting-state scoring.',flush=True)
        migrate_content()
        assert not any(checks().values()),'Competition starting state earned credit'
        engine_score(RES,'starting',0)
        starting=Snapshot(BACKUP/'competition-start',targets,packages)
        print('Running full 40-check solution rehearsal; public forensic answers stay blank.',flush=True)
        full_repair(initial.uuid)
        data=checks(); write(BACKUP/'solution-probes.json',json.dumps(data,indent=2),0o600)
        assert all(data.values()),'Full solution probe failures: '+','.join(str(i) for i,passed in data.items() if not passed)
        engine_score(RES,'solution',100)
        scenario.FORENSICS_FILES={issue:str(SHARED/('Forensic-Question-%d.txt'%number)) for issue,(number,_) in scenario.ANSWERS.items()}
        starting.restore()
        assert not any(checks().values()),'Restored competition state earned credit'
        engine_score(RES,'restored',0)
        print('Installing and checking encrypted production scoring.',flush=True)
        install_runtime()
        write(BACKUP/'completed.json',json.dumps({'automated_rehearsal':True,'solution_score':100,'starting_score':0,'manual_acceptance_pending':PENDING},indent=2),0o600)
        print('Automated finish passed: 100/100 solution, restored 0/100, encrypted 40-check production scorer active.')
        print('No reboot performed. Remaining manual acceptance is listed in /srv/summit-competition/Acceptance.html.')
        print('Private recovery records: '+str(BACKUP))
    except BaseException as error:
        write(BACKUP/'failure.txt',str(error)+'\n',0o600)
        print('Finishing failed; restoring pre-script state. Recovery records retained.',flush=True)
        try:
            initial.restore()
            scenario.FORENSICS_FILES={issue:str(SHARED/('Forensic-Question-%d.txt'%number)) for issue,(number,_) in scenario.ANSWERS.items()}
            health(scoring=True)
            assert checks()=={i:i in (16,32) for i in range(1,41)},'Restored pre-script probes differ'
            assert {n:rpm_state(n) for n in initial.rpms}==initial.rpms,'Restored packages differ'
            write(BACKUP/'rollback-verified.json',json.dumps({'verified':True,'score':6}),0o600)
        except BaseException as rollback:
            write(BACKUP/'rollback-failure.txt',str(rollback)+'\n',0o600)
            print('Automatic rollback needs console attention; inspect root recovery records.',file=sys.stderr)
        raise
if __name__=='__main__':
    if VERIFY:
        try: verify_only()
        except BaseException as error:
            public_status(False,'Read-only verification failed: '+str(error)); raise
    else: main()
