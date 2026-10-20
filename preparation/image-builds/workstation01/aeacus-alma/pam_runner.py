#!/usr/bin/env python3
"""PAM rehearsal runner: secrets on stdin, numeric result only on stdout."""
def response_for(style,prompt,user,operation,current,new):
    if style in (3,4): return None
    if style==2: return user
    if style!=1: raise ValueError('Unsupported PAM message style')
    if operation=='authenticate': return current
    lower=prompt.lower()
    if 'current' in lower or 'old' in lower: return current
    if 'new' in lower or 'retype' in lower: return new
    raise ValueError('Unknown password-change prompt')

def perform(service,user,operation,current,new=None,start_only=False):
    import ctypes as c
    pam=c.CDLL('libpam.so.0'); libc=c.CDLL('libc.so.6')
    class Message(c.Structure): _fields_=[('msg_style',c.c_int),('msg',c.c_char_p)]
    class Response(c.Structure): _fields_=[('resp',c.c_void_p),('resp_retcode',c.c_int)]
    callback_type=c.CFUNCTYPE(c.c_int,c.c_int,c.POINTER(c.POINTER(Message)),c.POINTER(c.POINTER(Response)),c.c_void_p)
    libc.calloc.argtypes=[c.c_size_t,c.c_size_t]; libc.calloc.restype=c.c_void_p
    libc.strdup.argtypes=[c.c_char_p]; libc.strdup.restype=c.c_void_p
    libc.free.argtypes=[c.c_void_p]; libc.free.restype=None
    @callback_type
    def converse(number,messages,out,unused):
        if not 0<number<=32: return 19
        array=c.cast(libc.calloc(number,c.sizeof(Response)),c.POINTER(Response))
        if not array: return 19
        try:
            for i in range(number):
                message=messages[i].contents
                value=response_for(message.msg_style,(message.msg or b'').decode(errors='replace'),user,operation,current,new)
                if value is not None:
                    array[i].resp=libc.strdup(value.encode())
                    if not array[i].resp: raise MemoryError()
            out[0]=array
            return 0
        except Exception:
            for i in range(number):
                if array[i].resp: libc.free(array[i].resp)
            libc.free(array)
            return 19
    class Conversation(c.Structure): _fields_=[('conv',callback_type),('appdata_ptr',c.c_void_p)]
    conversation=Conversation(converse,None); handle=c.c_void_p()
    pam.pam_start.argtypes=[c.c_char_p,c.c_char_p,c.POINTER(Conversation),c.POINTER(c.c_void_p)]
    pam.pam_end.argtypes=[c.c_void_p,c.c_int]
    for name in ('pam_authenticate','pam_acct_mgmt','pam_chauthtok'):
        getattr(pam,name).argtypes=[c.c_void_p,c.c_int]
    code=pam.pam_start(service.encode(),user.encode(),c.byref(conversation),c.byref(handle))
    if code==0:
        try:
            if not start_only:
                if operation=='change': code=pam.pam_chauthtok(handle,0)
                else:
                    code=pam.pam_authenticate(handle,0)
                    if code==0: code=pam.pam_acct_mgmt(handle,0)
        finally: pam.pam_end(handle,code)
    return code

if __name__=='__main__':
    import json,os,pwd,sys
    if sys.argv[1:]==['--self-test']:
        assert perform('other','summit-nonexistent','authenticate','',start_only=True)==0
        print('PAM ABI start/end: PASS (no authentication attempted)')
    else:
        request=json.load(sys.stdin)
        user=request['user']; operation=request['operation']
        assert operation in ('change','authenticate') and user=='summit-policy-test'
        identity=pwd.getpwnam(user)
        assert identity.pw_uid>=1000
        # PAM login needs privilege to create faillock tallies; password changes
        # need privilege for shadow writes. Non-root real UID preserves the
        # password-quality/history enforcement exercised by passwd.
        assert os.getuid()==0 and os.geteuid()==0,'PAM rehearsal must be launched by root'
        os.setgroups([identity.pw_gid])
        os.setresgid(identity.pw_gid,identity.pw_gid,identity.pw_gid)
        os.setresuid(identity.pw_uid,0,0)
        assert os.getuid()==identity.pw_uid and os.geteuid()==0
        code=perform('passwd' if operation=='change' else 'login',user,operation,request['current'],request.get('new'))
        print(json.dumps({'pam_code':code}))
