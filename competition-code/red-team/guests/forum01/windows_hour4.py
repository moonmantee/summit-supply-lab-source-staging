"""Fixed Windows service launch faults and dedicated MailEnable binary renames."""
import ctypes as C,importlib,json,os,pathlib,socket,subprocess,time,uuid
from four_hours import validate_event
from binary_rename import RenameFault,syncdir

SERVICES={('dc01','dns'):('DNS','business_launch_fault'),
 ('forum01','web'):('W3SVC','business_launch_fault'),('forum01','ftp'):('FTPSVC','business_launch_fault'),
 ('mail01','web'):('W3SVC','business_launch_fault'),('mail01','smtp'):('MESMTPCS','business_binary_rename'),
 ('mail01','imap'):('MEIMAPS','business_binary_rename')}
BINARIES={'smtp':r'C:\Program Files (x86)\Mail Enable\Bin64\MESMTPC.EXE',
          'imap':r'C:\Program Files (x86)\Mail Enable\Bin64\MEIMAPS.exe'}

def mapping(guest,target):
    try:return SERVICES[guest,target]
    except (KeyError,TypeError):raise ValueError('Unapproved Windows guest/service')

def launch_fault(service,path,baseline,stop,change,fresh,record,current=None):
    fresh();value={'phase':'PREPARED','service':service,'baseline':baseline,'planted_binary':path,'time':time.time()};record(value)
    fresh()
    stop();value['phase']='STOPPED';record(value)
    if current is not None:
        definition=lambda v:{k:item for k,item in v.items() if k!='state'}
        if definition(current())!=definition(baseline):raise ValueError('Contestant service definition change preserved')
    fresh();change(path);value['phase']='PLANTED';record(value)
    return {'outcome':'APPLIED'}

def private_acl(target):
    if target not in ('dns','web','ftp','smtp','imap'):raise ValueError('Invalid private state target')
    script=r"""$ErrorActionPreference='Stop';foreach($p in @('C:\ProgramData\SummitCaldera','C:\ProgramData\SummitCaldera\state','C:\ProgramData\SummitCaldera\state\hour4','C:\ProgramData\SummitCaldera\state\hour4\TARGET')){
 $i=Get-Item -LiteralPath $p -Force;if($i.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse state preserved'}
 foreach($a in (Get-Acl -LiteralPath $p).Access){$sid=$a.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;if($a.AccessControlType -eq 'Allow' -and $sid -notin @('S-1-5-18','S-1-5-32-544')){throw 'Private state ACL changed'}}
}""".replace('TARGET',target)
    subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-NonInteractive','-Command',script],check=True,capture_output=True,timeout=5)

def apply(native,event):
    validate_event(event,time.time());guest=socket.gethostname().lower()
    if os.name!='nt' or guest!=event['guest'] or not C.windll.shell32.IsUserAnAdmin():raise ValueError('Wrong privileged Windows guest')
    service,action=mapping(guest,event['target'])
    if action!=event['action'] or not native.healthy():raise ValueError('Unexpected action or changed native baseline')
    if type(native).__module__ not in ('windows_dns','windows_services'):raise ValueError('Unexpected native adapter')
    module=importlib.import_module(type(native).__module__)
    state=native.root/'hour4'/event['target']
    if not state.is_dir() or state.is_symlink():raise ValueError('Missing protected hour-four state')
    private_acl(event['target'])
    root=native.root.parent
    missing=root/'hour4-missing'/(service+'.exe')
    if missing.parent.exists() or missing.parent.is_symlink():raise ValueError('Unexpected missing-path replacement preserved')
    binary=BINARIES.get(event['target'],r'C:\Windows\System32\dns.exe')
    fault=RenameFault(binary,state,owner=None)
    fault.guards()
    def fresh():validate_event(event,time.time())
    with native.handle(mutate=True) as h:
        def stop():
            status=module.Status();module.checked(native.api.ControlService(h,1,C.byref(status)))
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                module.checked(native.api.QueryServiceStatus(h,C.byref(status)))
                if status.state==1:return
                time.sleep(.1)
            raise TimeoutError('Service did not stop within native bound')
        if action=='business_binary_rename':return fault.apply(stop,fresh)
        path='"'+str(missing)+'"'
        # Only this service's ImagePath changes. svchost.exe and all DLLs remain intact.
        def change(value):
            module.checked(native.api.ChangeServiceConfigW(h,0xffffffff,0xffffffff,0xffffffff,value,None,None,None,None,None,None))
            raw=native._query(h);cfg=C.cast(raw,C.POINTER(module.Config)).contents
            if cfg.binary!=value:raise ValueError('Service launch fault not observed')
        operation=state/'operation.json'
        if operation.exists():
            fault.protected(operation,private=True);history=state/'history';history.mkdir(mode=0o700,exist_ok=True);fault.protected(history,True,True)
            if len(list(history.iterdir()))>=64:raise ValueError('Hour-four evidence limit')
            os.rename(operation,history/(uuid.uuid4().hex+'.json'))
        return launch_fault(service,path,native.snapshot(),stop,change,fresh,lambda r:fault.publish('operation.json',r),native.snapshot)
