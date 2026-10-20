#!/usr/bin/env python3
"""Combined 100/100 repair proof, then exact restoration of the planted state.

Production Aeacus is never changed. Recovery archive contains real secrets:
retain it only inside its root-only guest directory.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from acceptance_helpers import require_state, secure_apache, secure_pam, scenario_fingerprint

SOURCE=Path(__file__).resolve().parent
PAM=Path('/var/backups/summit-shop01-pam-ezow1nGR/pam')
APACHE=Path('/var/backups/summit-shop01-apache-gqaohEcw/original-site.conf')
SSH_BACKUP=Path('/var/backups/summit-shop01-ssh-KY1iuaiy')
SITE=Path('/etc/apache2/sites-available/summit-shop.conf')
AUDIT=Path('/etc/audit/rules.d/70-summit-training.rules')
PROFILE=Path('/etc/apparmor.d/usr.sbin.rsyslogd')
MARKER='summit-shop-marker.service'
PATHS=[
 '/etc/passwd','/etc/shadow','/etc/group','/etc/gshadow',
 '/etc/sudoers.d/summit-training-support',
 '/etc/pam.d/common-auth','/etc/pam.d/common-account','/etc/pam.d/common-password',
 '/etc/security/faillock.conf','/etc/security/opasswd',
 '/etc/ssh/sshd_config.d/00-000-summit-training.conf',
 '/home/summit_editor/.ssh/authorized_keys',str(SITE),str(PROFILE),
 '/etc/systemd/journald.conf.d/zzzz-summit-training.conf',
 '/etc/apt/apt.conf.d/99zzzz-summit-training','/etc/ufw','/etc/default/ufw',
 '/etc/audit','/etc/cron.d/summit-shop-marker',
 '/etc/systemd/system/summit-shop-marker.service',
 '/etc/systemd/system/multi-user.target.wants/summit-shop-marker.service',
]
PATHS += ['/srv/summit-shop01-forensics/Forensic-Question-%d.txt'%i for i in (1,2,3)]
ACL_ONLY=['/etc/sudoers.d','/var/www/summit/index.php',
 '/etc/ssl/private','/etc/ssl/private/summit-shop01.key',
 '/home/summit_editor/.ssh','/opt/summit-shop-training/suid-marker']


def call(args, input=None):
    p=subprocess.run(args,input=input,text=True,capture_output=True,timeout=180)
    if p.returncode:
        # Command output can contain account data; preserve it privately instead.
        if BACKUP is not None:
            with (BACKUP/'commands.log').open('a') as f:
                f.write(repr(args)+'\n'+p.stdout+p.stderr+'\n')
        raise RuntimeError('Command failed: '+args[0]+' (private commands.log)')
    return p.stdout


def write(path,text,mode=0o644):
    p=Path(path)
    if p.is_symlink(): raise RuntimeError('Refusing symlink: '+str(p))
    p.write_text(text)
    p.chmod(mode)


def check_business():
    sys.path.insert(0,str(SOURCE/'probes'))
    import web
    for unit in ('ssh','sssd','apache2','rsyslog','summit-aeacus'):
        call(['systemctl','is-active','--quiet',unit])
    status,body=web.fetch('/')
    if status!=200 or not web.healthy_catalog(body) or web.fetch('/order-history.php')[0]!=200:
        raise RuntimeError('PHP storefront/order history failed')
    for user in ('jwang','summit_editor'):
        sudo=call(['sudo','-ll','-U',user])
        if 'RunAsUsers: ALL' not in sudo or '\tALL' not in sudo:
            raise RuntimeError('Required administrator sudo failed')
    call(['visudo','-c'])
    call(['/usr/sbin/sshd','-t'])
    # Check the retained approved organizer fixture with actual SSH/PAM.
    result=call(['ssh','-F','/dev/null','-i',str(SSH_BACKUP/'approved-key'),
                 '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5',
                 '-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519',
                 '-o','UserKnownHostsFile='+str(SSH_BACKUP/'known-hosts'),
                 'summit_editor@localhost','id -un'])
    if result.strip()!='summit_editor': raise RuntimeError('Actual editor SSH failed')


def validate(phase,secure):
    p=subprocess.run(['bash',str(SOURCE/'validate-probes.sh')],stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT,text=True,timeout=900)
    (BACKUP/(phase+'-engine.log')).write_text(p.stdout)
    if p.returncode: raise RuntimeError('Native Aeacus validation failed; private '+phase+'-engine.log')
    data=json.loads(Path('/home/jwang/shop01-probe-validation.json').read_text())
    require_state(data,secure)
    (BACKUP/(phase+'.json')).write_text(json.dumps(data,indent=2)+'\n')
    shutil.copy2('/home/jwang/shop01-probe-validation-report.html',BACKUP/(phase+'-report.html'))
    check_business()
    print(phase+': all 40 '+('PASS; Aeacus 100/100' if secure else 'FAIL; Aeacus 0/100')+'; business/recovery checks PASS',flush=True)


def capture():
    existing=[p for p in PATHS if os.path.lexists(p)]
    # Only the service enablement link is expected to be a symlink.
    for p in existing+ACL_ONLY:
        if Path(p).is_symlink() and p!='/etc/systemd/system/multi-user.target.wants/'+MARKER:
            raise RuntimeError('Unexpected symlink '+p)
    (BACKUP/'existing.json').write_text(json.dumps(existing))
    trees={p:sorted(str(child.relative_to(p)) for child in Path(p).rglob('*'))
           for p in ('/etc/ufw','/etc/audit')}
    (BACKUP/'trees.json').write_text(json.dumps(trees))
    call(['tar','--acls','--xattrs','--numeric-owner','-cpf',str(BACKUP/'planted.tar'),'-C','/']+
         [p.lstrip('/') for p in existing])
    (BACKUP/'metadata.acl').write_text(call(['getfacl','-p']+existing+ACL_ONLY))
    (BACKUP/'iptables.rules').write_text(call(['iptables-save']))
    (BACKUP/'ip6tables.rules').write_text(call(['ip6tables-save']))
    (BACKUP/'audit-runtime.txt').write_text(call(['auditctl','-l']))
    if (BACKUP/'audit-runtime.txt').read_text().strip()!='No rules':
        raise RuntimeError('Audit runtime changed; refusing to clear existing rules')
    (BACKUP/'holds.txt').write_text(call(['apt-mark','showhold']))
    if call(['ufw','status']).strip()!='Status: inactive': raise RuntimeError('Expected planted firewall inactive')
    units=[('auditd','disabled')]
    if str(Path('/etc/systemd/system')/MARKER) in existing: units.append((MARKER,'enabled'))
    for unit,state in units:
        p=subprocess.run(['systemctl','is-enabled',unit],text=True,capture_output=True)
        if p.stdout.strip()!=state: raise RuntimeError('Unexpected enablement '+unit)
    if len(units)>1: call(['systemctl','is-active','--quiet',MARKER])
    (BACKUP/'ready').write_text('Complete planted recovery snapshot\n')


def repair():
    call(['userdel','contractor_lab'])
    call(['userdel','-f','summit_rootalias'])
    for user in ('summit_employee','nobody'): call(['gpasswd','-d',user,'sudo'])
    Path('/etc/sudoers.d/summit-training-support').unlink()
    import secrets
    hashed=call(['openssl','passwd','-6','-stdin'],input=secrets.token_urlsafe(32)+'\n').strip()
    call(['chpasswd','-e'],input='summit_employee:'+hashed+'\n')
    call(['chage','-M','90','summit_employee'])
    auth,account,password=secure_pam(*[(PAM/name).read_text() for name in ('common-auth','common-account','common-password')])
    for name,text in zip(('common-auth','common-account','common-password'),(auth,account,password)):
        write('/etc/pam.d/'+name,text)
    write('/etc/security/faillock.conf','deny=5\nfail_interval=900\nunlock_time=900\nlocal_users_only\nadmin_group=sudo\n')
    write('/etc/ssh/sshd_config.d/00-000-summit-training.conf',
          'PermitRootLogin no\nPermitEmptyPasswords no\nAllowUsers jwang summit_editor\n')
    metadata=json.loads(Path('/var/lib/summit-shop01/private.json').read_text())
    keypath=Path('/home/summit_editor/.ssh/authorized_keys')
    lines=keypath.read_text().splitlines()
    approved=[l for l in lines if metadata['approved_key_blob'] in l.split()]
    if len(approved)!=1: raise RuntimeError('Expected one approved editor key')
    write(keypath,approved[0]+'\n',0o600)
    call(['setfacl','-b','/home/summit_editor/.ssh',str(keypath)])
    Path('/home/summit_editor/.ssh').chmod(0o700)
    call(['/usr/sbin/sshd','-t']); call(['systemctl','reload','ssh'])
    # Repair scoped ACLs/modes only; preserve application, key and credential contents.
    call(['setfacl','-b','/etc/shadow','/etc/sudoers.d',str(SITE),
          '/var/www/summit/index.php','/etc/ssl/private/summit-shop01.key'])
    call(['setfacl','-k','/etc/sudoers.d'])
    call(['chown','root:shadow','/etc/shadow']); Path('/etc/shadow').chmod(0o640)
    for path,mode in [('/etc/sudoers.d',0o755),(str(SITE),0o644),('/var/www/summit/index.php',0o644),
                      ('/etc/ssl/private/summit-shop01.key',0o600),('/etc/ssl/private',0o710)]:
        Path(path).chmod(mode)
    write(SITE,secure_apache(APACHE.read_text()))
    call(['apache2ctl','-t']); call(['systemctl','reload','apache2'])
    import web
    if web.fetch('/training-fixtures/SUMMIT-ERROR-VALIDATION/marker.txt')[0]!=403:
        raise RuntimeError('Controlled Apache error fixture failed')
    if not web.wait_for_token(Path('/var/log/apache2/summit-error.log'),'SUMMIT-ERROR-VALIDATION'):
        raise RuntimeError('Apache error logging failed')
    text=PROFILE.read_text()
    import re
    text,count=re.subn(r'(?m)^(profile rsyslogd /usr/sbin/rsyslogd flags=\()([^)]*)(\) \{)$',
        lambda m:m[1]+','.join(f.strip() for f in m[2].split(',') if f.strip() and f.strip()!='complain')+m[3],text)
    if count!=1: raise RuntimeError('Unknown rsyslog profile')
    write(PROFILE,text); call(['apparmor_parser','-r',str(PROFILE)])
    write('/etc/systemd/journald.conf.d/zzzz-summit-training.conf','[Journal]\nStorage=persistent\n')
    write('/etc/apt/apt.conf.d/99zzzz-summit-training','APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n')
    call(['apt-mark','unhold','apache2','apache2-bin','apache2-data','apache2-utils'])
    call(['systemd-tmpfiles','--create','--prefix','/var/log/journal'])
    call(['systemctl','restart','systemd-journald']); call(['journalctl','--flush'])
    write(AUDIT,''.join('-w '+p+' -p wa -k '+k+'\n' for p,k in (
        ('/etc/passwd','summit_accounts'),('/etc/group','summit_accounts'),('/etc/shadow','summit_accounts'),
        ('/etc/sudoers','summit_privilege'),('/etc/sudoers.d','summit_privilege'))),0o600)
    call(['systemctl','enable','--now','auditd']); call(['augenrules','--load'])
    # Reuse the already rehearsed UFW policy; preserve standard ICMP/DHCP rules.
    call(['ufw','--force','reset'])
    for name in ('before.rules','before6.rules'):
        p=Path('/etc/ufw')/name
        write(p,'\n'.join(l for l in p.read_text().splitlines() if not
            (l.startswith('-A ') and '--dport' in l and any(' '+port+' ' in l for port in ('5353','1900'))))+'\n',0o640)
    for policy,direction in [('deny','incoming'),('allow','outgoing'),('deny','routed')]:
        call(['ufw','default',policy,direction])
    for port in ('80/tcp','443/tcp'): call(['ufw','allow',port])
    for source in ('10.77.10.50','10.77.10.1','10.77.30.1','10.77.70.10'):
        call(['ufw','allow','from',source,'to','any','port','22','proto','tcp'])
    call(['ufw','--force','enable'])
    Path('/etc/cron.d/summit-shop-marker').unlink(missing_ok=True)
    if Path('/etc/systemd/system/'+MARKER).exists(): call(['systemctl','disable','--now',MARKER])
    Path('/etc/systemd/system/'+MARKER).unlink(missing_ok=True)
    call(['systemctl','daemon-reload'])
    Path('/opt/summit-shop-training/suid-marker').chmod(0o755)
    if json.loads((SOURCE/'competition-manifest.json').read_text())['issues'][37]['category']=='Forensics':
        from forensic_helpers import SOLUTIONS
        for issue,answer in SOLUTIONS.items():
            p=Path('/srv/summit-shop01-forensics/Forensic-Question-%d.txt'%(issue-37))
            p.write_text('Organizer solution rehearsal\nAnswer = '+answer+'\n')


def restore():
    if not (BACKUP/'ready').is_file(): raise RuntimeError('Recovery snapshot incomplete')
    call(['ufw','--force','disable'])
    call(['auditctl','-D'])
    call(['systemctl','disable','--now','auditd'])
    existing=json.loads((BACKUP/'existing.json').read_text())
    # Remove only files created by UFW/augenrules in the two captured trees.
    # Do not recursively remove a directory if unexpected state has appeared.
    for folder,names in json.loads((BACKUP/'trees.json').read_text()).items():
        parent=Path(folder)
        added=[p for p in parent.rglob('*') if str(p.relative_to(parent)) not in names]
        for p in sorted(added,key=lambda p:len(p.parts),reverse=True):
            if p.is_dir() and not p.is_symlink(): p.rmdir()
            else: p.unlink()
    for path in PATHS:
        if path not in existing and os.path.lexists(path):
            p=Path(path)
            if p.is_dir() and not p.is_symlink(): raise RuntimeError('Unexpected created directory '+path)
            p.unlink()
    # Snapshot is private, locally created, exact scoped paths; do not accept external archives.
    call(['tar','--acls','--xattrs','--numeric-owner','-xpf',str(BACKUP/'planted.tar'),'-C','/'])
    call(['setfacl','--restore='+str(BACKUP/'metadata.acl')])
    call(['tar','--acls','--xattrs','--numeric-owner','-dpf',str(BACKUP/'planted.tar'),'-C','/'])
    packages=['apache2','apache2-bin','apache2-data','apache2-utils']
    holds=set((BACKUP/'holds.txt').read_text().splitlines())
    for p in packages: call(['apt-mark','hold' if p in holds else 'unhold',p])
    call(['apparmor_parser','-r',str(PROFILE)])
    call(['systemctl','daemon-reload'])
    if '/etc/systemd/system/'+MARKER in existing: call(['systemctl','enable','--now',MARKER])
    call(['systemctl','restart','systemd-journald'])
    call(['/usr/sbin/sshd','-t']); call(['systemctl','reload','ssh'])
    call(['apache2ctl','-t']); call(['systemctl','reload','apache2'])
    call(['iptables-restore'],input=(BACKUP/'iptables.rules').read_text())
    call(['ip6tables-restore'],input=(BACKUP/'ip6tables.rules').read_text())


BACKUP=None
def main():
    global BACKUP
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='shop01':
        raise RuntimeError('Run with sudo on shop01')
    os.umask(0o077)
    # Operate only from a private root-owned copy of the uploaded organizer code.
    if SOURCE.stat().st_uid!=0 or SOURCE.stat().st_mode & 0o077:
        raise RuntimeError('Private root-owned source required; use rehearse-all.sh')
    if len(sys.argv)>1:
        if len(sys.argv)!=3 or sys.argv[1]!='--restore': raise RuntimeError('Unknown arguments')
        candidate=Path(sys.argv[2])
        import re
        if (str(candidate.parent)!='/var/backups' or not re.fullmatch(r'summit-shop01-all-[A-Za-z0-9_]+',candidate.name)
            or candidate.is_symlink() or candidate.stat().st_uid!=0 or candidate.stat().st_mode & 0o077):
            raise RuntimeError('Expected private local combined recovery directory')
        BACKUP=candidate
        restore(); validate('manual-restored',False)
        return
    BACKUP=Path(tempfile.mkdtemp(prefix='summit-shop01-all-',dir='/var/backups'))
    (BACKUP/'source-hashes.json').write_text(json.dumps(scenario_fingerprint(SOURCE),sort_keys=True)+'\n')
    print('Private combined recovery: '+str(BACKUP),flush=True)
    check_business()
    validate('original-planted',False)
    capture()
    def interrupted(signum,frame): raise RuntimeError('Interrupted '+str(signum))
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    try:
        repair()
        validate('combined-repaired',True)
    except BaseException:
        print('Combined validation failed; restoring planted snapshot.',flush=True)
        try:
            restore()
            validate('failure-restored',False)
        except BaseException as recovery:
            print('RESTORATION NEEDS CONSOLE ATTENTION: '+str(recovery)+'; '+str(BACKUP),flush=True)
        raise
    try:
        restore()
        validate('restored-planted',False)
    except BaseException:
        print('RESTORATION NEEDS CONSOLE ATTENTION; recovery retained: '+str(BACKUP),flush=True)
        raise
    evidence={'backup':str(BACKUP),'repaired':json.loads((BACKUP/'combined-repaired.json').read_text()),
              'restored':json.loads((BACKUP/'restored-planted.json').read_text())}
    target=Path('/home/jwang/shop01-combined-rehearsal.json')
    write(target,json.dumps(evidence,indent=2)+'\n',0o600)
    import pwd
    owner=pwd.getpwnam('jwang'); os.chown(target,owner.pw_uid,owner.pw_gid)
    print('Combined 100/100 → restored 0/100 verified. Production scoring unchanged.',flush=True)


if __name__=='__main__': main()
