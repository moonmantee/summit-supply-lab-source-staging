"""Fixed popup launched with the active console user's token, never SYSTEM."""
import ctypes as C
from ctypes import wintypes as W
import os
import pathlib
import time
from windows_services import checked

class Startup(C.Structure):
    _fields_=[('cb',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR),
      ('x',W.DWORD),('y',W.DWORD),('width',W.DWORD),('height',W.DWORD),('charsx',W.DWORD),('charsy',W.DWORD),('fill',W.DWORD),('flags',W.DWORD),
      ('show',W.WORD),('reserved2size',W.WORD),('reserved2',C.c_void_p),('stdin',W.HANDLE),('stdout',W.HANDLE),('stderr',W.HANDLE)]
class Process(C.Structure):_fields_=[('process',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]

def popup(expires):
    if not time.time()<expires<=time.time()+15:raise ValueError('Expired notice')
    kernel=C.WinDLL('kernel32',use_last_error=True);wts=C.WinDLL('wtsapi32',use_last_error=True);adv=C.WinDLL('advapi32',use_last_error=True)
    kernel.WTSGetActiveConsoleSessionId.restype=W.DWORD
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    wts.WTSQueryUserToken.argtypes=[W.ULONG,C.POINTER(W.HANDLE)];wts.WTSQueryUserToken.restype=W.BOOL
    adv.CreateProcessAsUserW.argtypes=[W.HANDLE,W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,W.LPCWSTR,C.POINTER(Startup),C.POINTER(Process)]
    adv.CreateProcessAsUserW.restype=W.BOOL
    session=kernel.WTSGetActiveConsoleSessionId()
    if session in (0,0xffffffff):raise ValueError('No active interactive console')
    token=W.HANDLE();checked(wts.WTSQueryUserToken(session,C.byref(token)))
    try:
        si=Startup();si.cb=C.sizeof(si);si.desktop='winsta0\\default';pi=Process()
        exe=r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
        script=r'C:\ProgramData\SummitCalderaNotice\Show-Notice.ps1'
        command=C.create_unicode_buffer('"'+exe+'" -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+script+'" -Expires '+str(float(expires)))
        if not time.time()<expires:raise ValueError('Expired before popup launch')
        checked(adv.CreateProcessAsUserW(token,exe,command,None,None,False,0x08000000,None,r'C:\Windows\System32',C.byref(si),C.byref(pi)))
        kernel.CloseHandle(pi.thread);kernel.CloseHandle(pi.process)
        return {'outcome':'APPLIED','delivery':'LAUNCHED','session':session,'pid':pi.pid}
    finally:kernel.CloseHandle(token)
