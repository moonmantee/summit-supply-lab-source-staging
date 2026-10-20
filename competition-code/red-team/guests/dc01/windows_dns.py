"""Native SCM adapter: fixed DNS target. No start, enable or automatic repair API."""
import contextlib
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
import pathlib
import socket
import struct
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

class DNS:
    def __init__(self,root):
        if os.name!='nt' or socket.gethostname().lower()!='dc01':raise ValueError('Wrong native guest')
        self.root=pathlib.Path(root);self.baseline=self.root/'dns-baseline.json'
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
            service=checked(self.api.OpenServiceW(manager,'DNS',0x20000|1|4|(2|0x20 if mutate else 0)))
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
              'binary_sha256':hashlib.sha256(pathlib.Path(r'C:\Windows\System32\dns.exe').read_bytes()).hexdigest()}
    def capture(self):
        value=self.snapshot()
        if value['state']!=4 or value['start']!=2 or not self.dns_health():raise ValueError('DNS baseline unhealthy')
        with self.baseline.open('x',encoding='utf-8') as f:
            json.dump(value,f,sort_keys=True);f.flush();os.fsync(f.fileno())
        return value
    @staticmethod
    def dns_health():
        # Exact authoritative A-record query, no host resolver/cache fallback.
        token=os.urandom(2);q=b''.join(bytes([len(x)])+x.encode() for x in 'dc01.corp.summit.test'.split('.'))+b'\0\0\1\0\1'
        packet=token+b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'+q
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                s.settimeout(1);s.connect(('127.0.0.1',53));s.send(packet);reply=s.recv(4096)
            if len(reply)<12 or reply[:2]!=token or reply[3]&15 or not reply[2]&128:return False
            # Parse names and RDATA; don't accept an address merely embedded anywhere.
            def skip(offset):
                for _ in range(128):
                    if offset>=len(reply):raise ValueError('Short DNS name')
                    n=reply[offset]
                    if n&192==192:
                        if offset+2>len(reply):raise ValueError('Short pointer')
                        return offset+2
                    if n&192:raise ValueError('Invalid name')
                    offset+=1
                    if n==0:return offset
                    offset+=n
                raise ValueError('Long DNS name')
            offset=12
            questions,answers=struct.unpack('!HH',reply[4:8])
            if questions!=1 or answers>64:return False
            offset=skip(offset)+4
            for _ in range(answers):
                offset=skip(offset);typ,cls,ttl,n=struct.unpack('!HHIH',reply[offset:offset+10]);offset+=10
                data=reply[offset:offset+n];offset+=n
                if typ==1 and cls==1 and data==socket.inet_aton('10.77.40.10'):return True
            return False
        except (OSError,ValueError,struct.error):return False
    def healthy(self):
        try:return self.snapshot()==json.loads(self.baseline.read_text()) and self.dns_health()
        except Exception:return False
    def apply(self,event):
        validate_event(event,time.time())
        if not self.healthy():raise ValueError('DNS baseline changed or not repaired')
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
                failure=Failure(900,None,None,1,actions)
                checked(self.api.ChangeServiceConfig2W(h,2,C.byref(failure)))
                validate_event(event,time.time())
                flag=W.DWORD(0);checked(self.api.ChangeServiceConfig2W(h,4,C.byref(flag)))
            elif event['action']!='business_stop':raise ValueError('Unsupported DNS action')
            validate_event(event,time.time())
            status=Status();checked(self.api.ControlService(h,1,C.byref(status)))
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                checked(self.api.QueryServiceStatus(h,C.byref(status)))
                if status.state==1:return {'outcome':'APPLIED'}
                time.sleep(.2)
        return {'outcome':'FAILED'}
