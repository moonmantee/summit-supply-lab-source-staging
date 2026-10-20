"""Exact apache2.service native adapter: stop, disable startup, Restart=no only."""
import hashlib
import json
import math
import os
import pathlib
import socket
import stat
import subprocess
import time
import uuid

STATE=pathlib.Path('/var/lib/summit-caldera-business')
OVERLAY=pathlib.Path('/etc/systemd/system/apache2.service.d/90-summit-caldera-restart.conf')
RESTART_OFF=b'[Service]\nRestart=no\n'
UNIT='apache2.service'
FIELDS=('Id','FragmentPath','DropInPaths','Restart','UnitFileState','ActiveState','SubState')
ACTIONS=('business_stop','business_disable','business_restart_off','business_binary_rename')

def protected(path,directory=False):
    info=path.lstat()
    if (path.is_symlink() or info.st_uid!=0 or info.st_mode & 0o022
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError('Untrusted native resource')
    return info

def private_state():
    for path in (pathlib.Path('/var'),pathlib.Path('/var/lib'),STATE):protected(path,True)
    if STATE.stat().st_mode & 0o077:raise ValueError('Business state must be private')
    protected(STATE/'startup',True)
    for name in ('baseline.json','recovery.sqlite3','enabled','mutation.lock','restart-owned.conf','capture.json'):
        path=STATE/name
        if path.exists() or path.is_symlink():
            protected(path)
            if path.stat().st_mode & 0o077:raise ValueError('Private business record required')

def owned_overlay():
    if not OVERLAY.exists() and not OVERLAY.is_symlink():return False
    protected(OVERLAY)
    if OVERLAY.read_bytes()!=RESTART_OFF:raise ValueError('Competitor restart-policy replacement')
    proof=STATE/'restart-owned.conf'
    protected(proof)
    if not os.path.samestat(OVERLAY.lstat(),proof.lstat()):raise ValueError('Competitor restart-policy inode preserved')
    return True

def startup_snapshot():
    paths=list(pathlib.Path('/etc/systemd/system').rglob('apache2.service'))
    for level in '0123456S':paths.extend(pathlib.Path('/etc/rc'+level+'.d').glob('*apache2'))
    result={}
    for path in sorted(set(paths)):
        if not path.is_symlink():continue
        protected(path.parent,True)
        info=path.lstat()
        if info.st_uid!=0:raise ValueError('Untrusted startup link')
        result[str(path)]={'dev':info.st_dev,'ino':info.st_ino,'target':os.readlink(path)}
    return result

def syncdir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

class Apache:
    def __init__(self):
        private_state();self.baseline=json.loads((STATE/'baseline.json').read_text())
        if self.baseline['Id']!=UNIT or self.baseline['FragmentPath']!='/usr/lib/systemd/system/apache2.service':raise ValueError('Unexpected service baseline')
    def run(self,*args):
        return subprocess.run(['/usr/bin/systemctl',*args],check=True,capture_output=True,text=True,timeout=20).stdout
    def info(self):
        return dict(line.split('=',1) for line in self.run('show',UNIT,'--property='+','.join(FIELDS)).splitlines() if '=' in line)
    def verify(self):
        for path in (pathlib.Path('/etc'),pathlib.Path('/etc/systemd'),pathlib.Path('/etc/systemd/system'),OVERLAY.parent):protected(path,True)
        info=self.info();fragment=pathlib.Path(self.baseline['FragmentPath']);protected(fragment)
        if (info['Id']!=UNIT or info['FragmentPath']!=str(fragment)
                or hashlib.sha256(fragment.read_bytes()).hexdigest()!=self.baseline['fragment_sha256']):
            raise ValueError('Business service definition changed')
        from linux_binary import current
        if not current('apache_backend').ready():raise ValueError('Executable baseline not repaired')
        overlay=owned_overlay()
        # Allow the two recognized sides of an interrupted daemon-reload.
        # ready() still requires the complete original effective state.
        if info['DropInPaths'] not in ('',str(OVERLAY)):raise ValueError('Unrecognized service drop-in')
        if info['Restart'] not in ('no',self.baseline['Restart']):raise ValueError('Effective restart policy changed')
        if info['UnitFileState'] not in (self.baseline['UnitFileState'],'disabled'):raise ValueError('Unrecognized startup replacement')
        return info
    def ready(self):
        try:
            from recovery_guard import ensure
            ensure(self.run,self.baseline)
            info=self.verify()
            if (owned_overlay() or info['DropInPaths'] or info['Restart']!=self.baseline['Restart']
                    or info['ActiveState']!='active' or info['SubState']!='running'
                    or info['UnitFileState']!=self.baseline['UnitFileState']):return False
            if (STATE/'restart-owned.conf').exists() or (STATE/'capture.json').exists() or any((STATE/'startup').iterdir()):return False
            if startup_snapshot()!=self.baseline['startup']:return False
            with socket.create_connection(('127.0.0.1',443),timeout=2):return True
        except Exception:return False
    def observe_repair(self):
        from manual_observation import observe
        return observe(self,__name__)
    def helper(self,mode,action,expires):
        if action not in ACTIONS or mode not in ('apply','restore'):raise ValueError('Unapproved native action')
        # PID1 launches this fixed native helper outside the broker's read-only
        # filesystem namespace. The contact cannot invoke it as root.
        result=subprocess.run(['/usr/bin/systemd-run','--quiet','--wait','--collect','--unit=summit-business-'+uuid.uuid4().hex,
            '--property=Type=exec','--property=NoNewPrivileges=yes',
            '--property=ProtectHome=yes','--property=PrivateTmp=yes','--property=MemoryMax=64M',
            '--property=TasksMax=24','--property=RuntimeMaxSec=30',
            '/usr/bin/python3','/opt/summit-caldera-fixtures/apache_backend.py','--native',mode,action,str(expires)],
            check=False,capture_output=True,timeout=35)
        if result.returncode==78:raise ValueError('Native competitor-policy conflict preserved')
        result.check_returncode()
    def apply(self,action,expires):self.helper('apply',action,expires)
    def restore(self,action):
        self.verify()  # Report recognized replacements as CONFLICT before launching recovery.
        self.helper('restore',action,time.time()+15)
        if not self.ready():raise OSError('Business service did not return to baseline')
    def native_apply(self,action,expires):
        def fresh():
            now=time.time()
            if action not in ACTIONS or not math.isfinite(expires) or not now<expires<=now+15:raise ValueError('Expired native mutation')
        fresh()
        if not self.ready():raise ValueError('Native baseline unavailable')
        if action=='business_binary_rename':
            from linux_binary import current
            return current('apache_backend').apply(lambda:self.run('stop',UNIT),fresh)
        if action=='business_restart_off':
            fresh()
            proof=STATE/'restart-owned.conf'
            with proof.open('xb') as output:
                output.write(RESTART_OFF);output.flush();os.fchmod(output.fileno(),0o600);os.fsync(output.fileno())
            syncdir(STATE)
            fresh();os.link(proof,OVERLAY);syncdir(OVERLAY.parent)
            fresh()
            self.run('daemon-reload')
        elif action=='business_disable':
            # Capture exact baseline symlinks instead of letting systemctl disable
            # remove newer/custom links or rewrite SysV startup state.
            if startup_snapshot()!=self.baseline['startup']:raise ValueError('Startup topology changed')
            for index,(name,identity) in enumerate(sorted(self.baseline['startup'].items())):
                path=pathlib.Path(name)
                if not (path.name.startswith('S') or path.parent.name.endswith('.wants')):continue
                fresh();captured=STATE/'startup'/str(index)
                os.rename(path,captured);syncdir(captured.parent);syncdir(path.parent)
                info=captured.lstat()
                if (info.st_dev,info.st_ino)!=(identity['dev'],identity['ino']) or os.readlink(captured)!=identity['target']:
                    try:os.link(captured,path,follow_symlinks=False);captured.unlink()
                    except FileExistsError:pass
                    raise ValueError('Startup replacement preserved during capture')
            fresh();self.run('daemon-reload')
        fresh()
        self.run('stop',UNIT)
        info=self.info()
        if info['ActiveState']!='inactive':raise OSError('Scored service did not stop')
        if action=='business_disable' and info['UnitFileState']!='disabled':raise OSError('Startup was not disabled')
        if action=='business_restart_off' and info['Restart']!='no':raise OSError('Automatic restart was not disabled')
    def native_restore(self,action):
        if action=='business_binary_rename':raise ValueError('Hour-four executable repair is manual only')
        if action not in ACTIONS:raise ValueError('Unapproved restoration action')
        self.verify();info=self.info()
        claim=STATE/'capture.json'
        if claim.exists():
            protected(claim);name=json.loads(claim.read_text())['name']
            if (not name.startswith('.summit-captured-') or len(name)!=49
                    or any(c not in '0123456789abcdef' for c in name[17:])):raise ValueError('Invalid capture record')
            captured=OVERLAY.parent/name
            if captured.exists() or captured.is_symlink():
                proof=STATE/'restart-owned.conf'
                if (captured.is_symlink() or not proof.exists() or not os.path.samestat(captured.lstat(),proof.lstat())
                        or captured.read_bytes()!=RESTART_OFF):
                    try:os.link(captured,OVERLAY,follow_symlinks=False);syncdir(OVERLAY.parent)
                    except FileExistsError:pass
                    raise ValueError('Interrupted competitor capture re-exposed and preserved')
                captured.unlink();syncdir(OVERLAY.parent)
            claim.unlink();syncdir(STATE)
        if action=='business_restart_off' and owned_overlay():
            prior=OVERLAY.lstat()
            captured=OVERLAY.parent/('.summit-captured-'+uuid.uuid4().hex)
            with claim.open('x') as output:
                json.dump({'name':captured.name},output);output.flush();os.fchmod(output.fileno(),0o600);os.fsync(output.fileno())
            syncdir(STATE)
            os.rename(OVERLAY,captured)
            syncdir(OVERLAY.parent)
            current=captured.lstat()
            if (captured.is_symlink() or (current.st_dev,current.st_ino)!=(prior.st_dev,prior.st_ino)
                    or not stat.S_ISREG(current.st_mode) or captured.read_bytes()!=RESTART_OFF):
                try:os.link(captured,OVERLAY,follow_symlinks=False);syncdir(OVERLAY.parent)
                except FileExistsError:pass  # Preserve both replacements; never overwrite blue's new path.
                raise ValueError('Restart policy changed during capture')
            captured.unlink();syncdir(OVERLAY.parent);claim.unlink();syncdir(STATE);self.run('daemon-reload')
        elif owned_overlay():raise ValueError('Unexpected restart overlay for this action')
        elif action=='business_restart_off':self.run('daemon-reload')
        if action=='business_restart_off':
            proof=STATE/'restart-owned.conf'
            if proof.exists():protected(proof);proof.unlink();syncdir(STATE)
        if action=='business_disable':
            expected=dict(self.baseline['startup']);captured_links=[];current=startup_snapshot()
            for index,(name,identity) in enumerate(sorted(self.baseline['startup'].items())):
                captured=STATE/'startup'/str(index)
                if not captured.is_symlink():
                    if captured.exists():
                        try:os.link(captured,pathlib.Path(name),follow_symlinks=False);syncdir(pathlib.Path(name).parent)
                        except FileExistsError:pass
                        raise ValueError('Startup capture replaced; replacement preserved')
                    continue
                link=captured.lstat()
                if (link.st_dev,link.st_ino)!=(identity['dev'],identity['ino']) or os.readlink(captured)!=identity['target']:
                    try:os.link(captured,pathlib.Path(name),follow_symlinks=False);syncdir(pathlib.Path(name).parent)
                    except FileExistsError:pass
                    raise ValueError('Startup capture identity changed')
                if current.get(name)!=identity:expected.pop(name)
                captured_links.append((captured,pathlib.Path(name)))
            if current!=expected:raise ValueError('Competitor startup topology preserved')
            for captured,path in captured_links:
                # Exclusive hardlink preserves the original symlink inode and
                # cannot overwrite a competitor replacement at its old path.
                try:os.link(captured,path,follow_symlinks=False)
                except FileExistsError:
                    if not path.is_symlink() or not os.path.samestat(path.lstat(),captured.lstat()) or os.readlink(path)!=os.readlink(captured):
                        raise ValueError('Startup replacement during restore preserved')
                syncdir(path.parent)
                captured.unlink();syncdir(captured.parent)
            self.run('daemon-reload')
        elif info['UnitFileState']!=self.baseline['UnitFileState']:raise ValueError('Competitor startup change preserved')
        # A blue-team start is already a successful repair; do not stop it again.
        if info['ActiveState'] not in ('active','activating'):self.run('start',UNIT)

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',nargs=3,metavar=('MODE','ACTION','EXPIRES'))
    args=parser.parse_args()
    if os.geteuid()!=0 or socket.gethostname()!='shop01':raise ValueError('Root on shop01 required')
    if args.native:
        mode,action,expires=args.native
        if mode not in ('apply','restore') or action not in ACTIONS:raise ValueError('Unapproved helper operation')
        # PID1 owns the helper lifetime. This lock remains held even if the
        # broker dies and releases its SQLite transaction during mutation.
        import fcntl
        private_state()
        fd=os.open(STATE/'mutation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            protected(STATE/'mutation.lock');fcntl.flock(fd,fcntl.LOCK_EX)
            backend=Apache()
            if mode=='apply':backend.native_apply(action,float(expires))
            else:backend.native_restore(action)
        except ValueError:raise SystemExit(78)
        finally:os.close(fd)
    else:print(json.dumps({'ready':Apache().ready()}))

if __name__=='__main__':main()
