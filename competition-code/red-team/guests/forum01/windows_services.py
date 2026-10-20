"""Native SCM adapter: fixed forum IIS/FTP targets. No start, enable or automatic repair API."""
import contextlib
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
import pathlib
import socket
import urllib.request
import time
from windows_worker import validate_event

class Status(C.Structure):
    _fields_=[(n,W.DWORD) for n in ('type','state','accepted','exit','specific','checkpoint','hint')]
class Config(C.Structure):
    _fields_=[('type',W.DWORD),('start',W.DWORD),('error',W.DWORD),('binary',W.LPWSTR),('group',W.LPWSTR),('tag',W.DWORD),('dependencies',C.c_void_p),('account',W.LPWSTR),('display',W.LPWSTR)]
class Action(C.Structure):_fields_=[('type',W.DWORD),('delay',W.DWORD)]
class Failure(C.Structure):
    _fields_=[('reset',W.DWORD),('reboot',W.LPWSTR),('command',W.LPWSTR),('count',W.DWORD),('actions',C.POINTER(Action))]

def checked(ok):
    if not ok:raise C.WinError(C.get_last_error())
    return ok

TARGETS={'web':('W3SVC',r'C:\Windows\System32\inetsrv\iisw3adm.dll'),
         'ftp':('FTPSVC',r'C:\Windows\System32\inetsrv\ftpsvc.dll')}

def application_health(target):
    try:
        if target=='web':
            request=urllib.request.Request('http://127.0.0.1/')
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=2) as response:return response.status==200
        if target=='ftp':
            with socket.create_connection(('10.77.30.20',21),timeout=2) as connection:return connection.recv(512).startswith(b'220')
        return False
    except (OSError,ValueError):return False

class NativeService:
    def __init__(self,root,target):
        if os.name!='nt' or socket.gethostname().lower()!='forum01':raise ValueError('Wrong native guest')
        self.root=pathlib.Path(root);self.baseline=self.root/'services-baseline.json'
        if target not in TARGETS:raise ValueError('Wrong service target')
        self.target=target;self.service,self.dll=TARGETS[target]
        self.api=C.WinDLL('advapi32',use_last_error=True)
        signatures={
          'OpenSCManagerW':([W.LPCWSTR,W.LPCWSTR,W.DWORD],W.HANDLE),
          'OpenServiceW':([W.HANDLE,W.LPCWSTR,W.DWORD],W.HANDLE),
          'CloseServiceHandle':([W.HANDLE],W.BOOL),
          'QueryServiceStatus':([W.HANDLE,C.POINTER(Status)],W.BOOL),
          'QueryServiceConfigW':([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)],W.BOOL),
          'QueryServiceConfig2W':([W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)],W.BOOL),
          'QueryServiceObjectSecurity':([W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)],W.BOOL),
          'ControlService':([W.HANDLE,W.DWORD,C.POINTER(Status)],W.BOOL),
          'ChangeServiceConfigW':([W.HANDLE,W.DWORD,W.DWORD,W.DWORD,W.LPCWSTR,W.LPCWSTR,C.c_void_p,W.LPCWSTR,W.LPCWSTR,W.LPCWSTR,W.LPCWSTR],W.BOOL),
          'ChangeServiceConfig2W':([W.HANDLE,W.DWORD,C.c_void_p],W.BOOL)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.api,name);fn.argtypes=args;fn.restype=result
    @contextlib.contextmanager
    def handle(self,mutate=False):
        manager=checked(self.api.OpenSCManagerW(None,None,1))
        service=None
        try:
            service=checked(self.api.OpenServiceW(manager,self.service,0x20000|1|4|(2|0x20 if mutate else 0)))
            yield service
        finally:
            if service:self.api.CloseServiceHandle(service)
            self.api.CloseServiceHandle(manager)
    def _query(self,h,level=None):
        size=W.DWORD();buf=C.create_string_buffer(8192)
        if level is None:checked(self.api.QueryServiceConfigW(h,buf,len(buf),C.byref(size)))
        else:checked(self.api.QueryServiceConfig2W(h,level,buf,len(buf),C.byref(size)))
        return buf
    def snapshot(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\Services\\'+self.service+'\\Parameters') as key:
            dll=winreg.ExpandEnvironmentStrings(winreg.QueryValueEx(key,'ServiceDll')[0])
        if os.path.normcase(dll)!=os.path.normcase(self.dll):raise ValueError('Unexpected service DLL mapping')
        with self.handle() as h:
            raw=self._query(h);cfg=C.cast(raw,C.POINTER(Config)).contents
            deps=[];offset=cfg.dependencies
            if offset:
                while True:
                    item=C.wstring_at(offset)
                    if not item:break
                    deps.append(item);offset+=(len(item)+1)*C.sizeof(C.c_wchar)
            raw2=self._query(h,2);fail=C.cast(raw2,C.POINTER(Failure)).contents
            status=Status();checked(self.api.QueryServiceStatus(h,C.byref(status)))
            security=C.create_string_buffer(65536);size=W.DWORD()
            checked(self.api.QueryServiceObjectSecurity(h,1|2|4,security,len(security),C.byref(size)))
            return {'state':status.state,'start':cfg.start,'type':cfg.type,'error':cfg.error,
              'binary':cfg.binary,'account':cfg.account,'dependencies':deps,
              'failure':{'reset':fail.reset,'reboot':fail.reboot or '', 'command':fail.command or '',
                         'actions':[[fail.actions[i].type,fail.actions[i].delay] for i in range(fail.count)]},
              'noncrash':C.cast(self._query(h,4),C.POINTER(W.DWORD)).contents.value,
              'delayed':C.cast(self._query(h,3),C.POINTER(W.DWORD)).contents.value,
              'security':security.raw[:size.value].hex(),
              'binary_sha256':hashlib.sha256(pathlib.Path(r'C:\Windows\System32\svchost.exe').read_bytes()).hexdigest(),
              'service_dll':self.dll,'service_dll_sha256':hashlib.sha256(pathlib.Path(self.dll).read_bytes()).hexdigest()}
    def healthy(self):
        try:return self.snapshot()==json.loads(self.baseline.read_text())[self.target] and application_health(self.target)
        except Exception:return False
    def apply(self,event):
        validate_event(event,time.time())
        if event['target']!=self.target:raise ValueError('Target mismatch')
        if not self.healthy():raise ValueError('Service baseline changed or not repaired')
        if event['action'] in ('business_binary_rename','business_launch_fault'):
            from windows_hour4 import apply
            return apply(self,event)
        # Worker has already durably recorded ACCEPTED before this fixed mutation.
        with self.handle(mutate=True) as h:
            validate_event(event,time.time())
            if event['action']=='business_disable':
                checked(self.api.ChangeServiceConfigW(h,0xffffffff,4,0xffffffff,None,None,None,None,None,None,None))
            elif event['action']=='business_restart_off':
                actions=(Action*1)(Action(0,0))
                failure=Failure(json.loads(self.baseline.read_text())[self.target]['failure']['reset'],None,None,1,actions)
                checked(self.api.ChangeServiceConfig2W(h,2,C.byref(failure)))
                validate_event(event,time.time())
                flag=W.DWORD(0);checked(self.api.ChangeServiceConfig2W(h,4,C.byref(flag)))
            elif event['action']!='business_stop':raise ValueError('Unsupported service action')
            validate_event(event,time.time())
            status=Status();checked(self.api.ControlService(h,1,C.byref(status)))
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                checked(self.api.QueryServiceStatus(h,C.byref(status)))
                if status.state==1:return {'outcome':'APPLIED'}
                time.sleep(.2)
        return {'outcome':'FAILED'}

class Services:
    def __init__(self,root):
        self.root=pathlib.Path(root);self.baseline=self.root/'services-baseline.json'
        self.services={target:NativeService(root,target) for target in TARGETS}
    def capture(self):
        values={target:service.snapshot() for target,service in self.services.items()}
        if any(v['state']!=4 or v['start']!=2 or not application_health(target) for target,v in values.items()):raise ValueError('Forum baseline unhealthy')
        if any(a[0] in (1,2,3) for a in values['web']['failure']['actions']):raise ValueError('Unexpected web restart baseline')
        if not any(a[0]==1 for a in values['ftp']['failure']['actions']):raise ValueError('Missing FTP restart baseline')
        with self.baseline.open('x',encoding='utf-8') as f:json.dump(values,f,sort_keys=True);f.flush();os.fsync(f.fileno())
        return values
    def healthy(self):return all(service.healthy() for service in self.services.values())
    def apply(self,event):
        validate_event(event,time.time())
        if not self.healthy():raise ValueError('Unrepaired forum service')
        return self.services[event['target']].apply(event)
