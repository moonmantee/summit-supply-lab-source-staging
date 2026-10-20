"""Fail closed unless exact independent business recovery is active and intact."""
import hashlib,pathlib,stat
APP=pathlib.Path('/opt/summit-caldera-fixtures')
UNITROOT=pathlib.Path('/etc/systemd/system')
TIMER='summit-caldera-business-recovery.timer';SERVICE='summit-caldera-business-recovery.service'
def digest(path):
    info=path.lstat()
    if path.is_symlink() or info.st_uid!=0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):raise ValueError('Untrusted recovery resource')
    return hashlib.sha256(path.read_bytes()).hexdigest()
def inspect(run,unit):
    return dict(line.split('=',1) for line in run('show',unit,'--property=Id,FragmentPath,DropInPaths,ActiveState,UnitFileState,ExecStart,Triggers,NeedDaemonReload').splitlines() if '=' in line)
def effective(run):
    timer=inspect(run,TIMER);service=inspect(run,SERVICE)
    if timer['ActiveState']!='active' or timer['UnitFileState']!='enabled' or timer['Triggers']!=SERVICE:raise ValueError('Independent recovery timer unavailable')
    for unit,info in ((TIMER,timer),(SERVICE,service)):
        if info['Id']!=unit or info['FragmentPath']!=str(UNITROOT/unit) or info['DropInPaths'] or info.get('NeedDaemonReload')!='no':raise ValueError('Independent recovery definition changed or stale')
    command='{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 /opt/summit-caldera-fixtures/business_actions.py recover ;'
    if not service['ExecStart'].startswith(command) or service['ExecStart'].count('{ path=')!=1:raise ValueError('Independent recovery executable changed')
def capture(run,backend):
    if backend not in ('apache_backend.py','mariadb_backend.py'):raise ValueError('Unapproved recovery backend')
    effective(run)
    return {'units':{name:digest(UNITROOT/name) for name in (TIMER,SERVICE)},
        'sources':{name:digest(APP/name) for name in (backend,'business_actions.py','first_three_hours.py','recovery_guard.py','manual_observation.py','four_hours.py','binary_rename.py','linux_binary.py')}}
def ensure(run,baseline):
    effective(run);proof=baseline['recovery']
    if set(proof['units'])!={TIMER,SERVICE}:raise ValueError('Missing recovery proof')
    if set(proof['sources']) not in ({'apache_backend.py','business_actions.py','first_three_hours.py','recovery_guard.py','manual_observation.py','four_hours.py','binary_rename.py','linux_binary.py'}, {'mariadb_backend.py','business_actions.py','first_three_hours.py','recovery_guard.py','manual_observation.py','four_hours.py','binary_rename.py','linux_binary.py'}):raise ValueError('Invalid recovery source roster')
    for root,kind in ((UNITROOT,'units'),(APP,'sources')):
        for name,expected in proof[kind].items():
            if digest(root/name)!=expected:raise ValueError('Independent recovery resource changed')
