"""Observe contestant repairs; only archive private evidence, never change a service."""
import fcntl,importlib,json,os,pathlib,socket,time,uuid
from recovery_guard import ensure
def observe(backend,module_name):
    if module_name not in ('apache_backend','mariadb_backend'):raise ValueError('Unapproved adapter')
    m=importlib.import_module(module_name);m.private_state();ensure(backend.run,backend.baseline)
    fd=os.open(m.STATE/'mutation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        m.protected(m.STATE/'mutation.lock')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        info=backend.verify()
        if (info['ActiveState']!='active' or info['SubState']!='running' or info['DropInPaths']
            or info['Restart']!=backend.baseline['Restart'] or info['UnitFileState']!=backend.baseline['UnitFileState']
            or m.OVERLAY.exists() or m.OVERLAY.is_symlink() or (m.STATE/'capture.json').exists()):return False
        current=m.startup_snapshot();original=backend.baseline['startup']
        if set(current)!=set(original) or any(current[name]['target']!=original[name]['target'] for name in original):return False
        captured=list((m.STATE/'startup').iterdir())
        identities=dict(enumerate(sorted(original.items())))
        for path in captured:
            if not path.name.isdecimal() or int(path.name) not in identities:raise ValueError('Unknown private capture')
            name,identity=identities[int(path.name)];entry=path.lstat()
            if (not path.is_symlink() or entry.st_uid!=0 or (entry.st_dev,entry.st_ino)!=(identity['dev'],identity['ino'])
                or os.readlink(path)!=identity['target']):raise ValueError('Private startup evidence changed')
        proof=m.STATE/'restart-owned.conf'
        if proof.exists():
            m.protected(proof)
            if proof.read_bytes()!=m.RESTART_OFF:raise ValueError('Private restart proof changed')
        with socket.create_connection(('10.77.50.20',3306) if module_name=='mariadb_backend' else ('127.0.0.1',443),timeout=2):pass
        # No systemctl start/enable/reload and no /etc write occurs here.
        # Blue already repaired effective state. Retain old private captures and
        # recognize blue-created startup inodes for subsequent authorized actions.
        if captured or proof.exists() or current!=original:
            root=m.STATE/'contestant-repairs'
            if not root.exists():root.mkdir(mode=0o700)
            m.protected(root,True)
            if len(list(root.iterdir()))>=1000:raise ValueError('Repair archive limit')
            archive=root/uuid.uuid4().hex;archive.mkdir(mode=0o700)
            with (archive/'before.json').open('x') as f:json.dump(backend.baseline,f);os.fchmod(f.fileno(),0o600);f.flush();os.fsync(f.fileno())
            for path in captured:os.rename(path,archive/('startup-'+path.name))
            if proof.exists():os.rename(proof,archive/'restart-owned.conf')
            baseline={**backend.baseline,'startup':current}
            temp=m.STATE/('baseline.manual-'+uuid.uuid4().hex)
            with temp.open('x') as f:json.dump(baseline,f);os.fchmod(f.fileno(),0o600);f.flush();os.fsync(f.fileno())
            os.replace(temp,m.STATE/'baseline.json');m.syncdir(m.STATE);backend.baseline=baseline
        return backend.ready()
    finally:os.close(fd)
