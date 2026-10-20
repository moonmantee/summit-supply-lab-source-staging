"""No-clobber rename primitive; called only by fixed, locally bound adapters.

There is deliberately no restoration/start timer or controller-supplied pathname.
The private original is an independent copy. Blue can rename the public disabled
file back and start the service; changed replacements remain untouched.
"""
import ctypes,hashlib,json,os,pathlib,stat,time,uuid

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def syncdir(path):
    if os.name=='posix':
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

def noreplace(source,destination):
    if os.name=='nt':os.rename(source,destination);return
    libc=ctypes.CDLL(None,use_errno=True);fn=libc.renameat2
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
    fd=os.open(source.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if fn(fd,os.fsencode(source.name),fd,os.fsencode(destination.name),1):
            error=ctypes.get_errno();raise OSError(error,os.strerror(error))
        os.fsync(fd)
    finally:os.close(fd)

class RenameFault:
    def __init__(self,executable,state,owner=0,check_ancestors=True):
        self.executable=pathlib.Path(executable);self.state=pathlib.Path(state)
        self.disabled=self.executable.with_name(self.executable.name+'.summit-hour4-disabled')
        self.owner=owner;self.check_ancestors=check_ancestors
    def protected(self,path,directory=False,private=False):
        s=path.lstat()
        if path.is_symlink() or getattr(s,'st_file_attributes',0)&0x400:raise ValueError('Symlink/reparse resource preserved')
        if not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)):raise ValueError('Unexpected resource type')
        if os.name=='posix' and (s.st_uid!=self.owner or s.st_mode&(0o077 if private else 0o022)):raise ValueError('Unprotected resource')
        if not directory and s.st_nlink!=1:raise ValueError('Shared file identity')
        return s
    def guards(self):
        self.protected(self.state,True,True)
        if self.check_ancestors:
            for root in (self.executable.parent,self.state.parent):
                for p in (root,*root.parents):self.protected(p,True)
    def identity(self):
        s=self.protected(self.executable)
        return {'dev':s.st_dev,'ino':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns,
                'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid,'sha256':digest(self.executable)}
    def publish(self,name,value):
        target=self.state/name
        if target.exists() or target.is_symlink():self.protected(target,private=True)
        temp=self.state/('.'+name+'-'+uuid.uuid4().hex)
        with temp.open('x') as out:
            if os.name=='posix':os.fchmod(out.fileno(),0o600)
            json.dump(value,out,sort_keys=True);out.flush();os.fsync(out.fileno())
        os.replace(temp,target);syncdir(self.state)
    def capture(self,expected_sha256):
        self.guards();before=self.identity()
        if before['sha256']!=expected_sha256:raise ValueError('Executable baseline mismatch')
        if any(self.state.iterdir()):raise ValueError('Existing hour-four capture preserved')
        if self.disabled.exists() or self.disabled.is_symlink():raise ValueError('Existing disabled destination preserved')
        original=self.state/'original'
        with self.executable.open('rb') as src,original.open('xb') as out:
            if os.name=='posix':os.fchmod(out.fileno(),0o600)
            while True:
                block=src.read(1024*1024)
                if not block:break
                out.write(block)
            out.flush();os.fsync(out.fileno())
        if self.identity()!=before or digest(original)!=expected_sha256:raise ValueError('Concurrent executable change; capture incomplete')
        self.publish('baseline.json',before)
    def baseline(self):
        self.guards();p=self.state/'baseline.json';self.protected(p,private=True)
        return json.loads(p.read_text())
    def ready(self):
        try:
            baseline=self.baseline();current=self.identity()
            return all(current[k]==baseline[k] for k in ('sha256','mode','uid','gid','size'))
        except (OSError,ValueError):return False
    def apply(self,stop,fresh):
        self.guards()
        if not self.ready():raise ValueError('Unrepaired executable or changed baseline')
        if self.disabled.exists() or self.disabled.is_symlink():raise ValueError('Disabled destination already exists')
        before=self.identity();baseline=self.baseline();original=self.state/'original';self.protected(original,private=True)
        if digest(original)!=baseline['sha256']:raise ValueError('Private original changed')
        op=self.state/'operation.json'
        if op.exists():
            self.protected(op,private=True)
            history=self.state/'history';history.mkdir(mode=0o700,exist_ok=True);self.protected(history,True,True)
            if len(list(history.iterdir()))>=64:raise ValueError('Hour-four evidence limit')
            os.rename(op,history/(uuid.uuid4().hex+'.json'));syncdir(history)
        fresh();record={'phase':'PREPARED','time':time.time(),'before':before,'disabled':str(self.disabled)}
        self.publish('operation.json',record)
        fresh()
        stop();record['phase']='STOPPED';self.publish('operation.json',record)
        fresh()
        if self.identity()!=before:raise ValueError('Contestant executable replacement preserved')
        fresh()
        noreplace(self.executable,self.disabled);syncdir(self.executable.parent)
        try:
            moved=self.protected(self.disabled)
            if (moved.st_dev,moved.st_ino)!=(before['dev'],before['ino']) or digest(self.disabled)!=before['sha256']:raise ValueError('Renamed object conflict')
        except (OSError,ValueError) as conflict:
            record['phase']='CONFLICT'
            try:self.publish('operation.json',record)
            finally:
                # A replacement raced the syscall. Return it without replacing
                # anything subsequently created at the original pathname.
                try:noreplace(self.disabled,self.executable);syncdir(self.executable.parent)
                except OSError:pass
            raise ValueError('Renamed object conflict; contestant files preserved; inspect locally') from conflict
        record['phase']='RENAMED';self.publish('operation.json',record)
        return {'outcome':'APPLIED'}
