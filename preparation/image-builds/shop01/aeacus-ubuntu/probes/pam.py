"""Conservative local-PAM policy probes; unknown control flow fails closed."""
import re
from pathlib import Path
from common import ProbeError, read

ISSUES = (7,8,9,10)

def policy(text):
    data={}
    for raw in text.splitlines():
        line=raw.split('#',1)[0].strip()
        if not line: continue
        if '=' in line:
            key,value=line.split('=',1); data[key.strip()]=value.strip()
        else: data[line]=True
    return data

def stack(text):
    entries=[]
    for raw in text.splitlines():
        line=raw.split('#',1)[0].strip()
        if not line: continue
        m=re.fullmatch(r'(auth|account|password|session)\s+(\[[^]]+\]|\S+)\s+(\S+)(?:\s+(.*))?',line)
        if not m: raise ProbeError('Unsupported PAM syntax')
        entries.append({'type':m[1],'control':m[2],'module':Path(m[3]).name,'args':policy((m[4] or '').replace(' ','\n'))})
    return entries

def module_config(entries,module,base):
    matches=[(i,e) for i,e in enumerate(entries) if e['module']==module]
    if len(matches)!=1: return None,None,{}
    i,e=matches[0]
    settings=dict(base); settings.update(e['args'])
    return i,e,settings

def integer(settings,name,default):
    try: return int(settings.get(name,default))
    except (TypeError,ValueError): return None

def evaluate(issue,d):
    if issue in (7,8,10):
        entries=stack(d.get('password',''))
        unix=next((i for i,e in enumerate(entries) if e['module']=='pam_unix.so'),None)
        module='pam_pwhistory.so' if issue==10 else 'pam_pwquality.so'
        i,e,settings=module_config(entries,module,d.get('history' if issue==10 else 'quality',{}))
        if e is None or unix is None or i>=unix or e['control'] not in ('required','requisite'): return False
        # Reject preceding control flow that can skip enforcement. A local-user
        # guard is accepted only for the explicitly local password-history step.
        for prior in entries[:i]:
            if prior['control'] not in ('required','requisite','optional'):
                if not (issue==10 and prior['module']=='pam_localuser.so' and prior['control']=='[success=ok default=1]' and entries[i-1] is prior): return False
        if issue==7:
            minimum=integer(settings,'minlen',8)
            credits=[integer(settings,k,0) for k in ('dcredit','ucredit','lcredit','ocredit')]
            return minimum is not None and minimum>=14 and all(c is not None and c<=0 for c in credits)
        if issue==8: return integer(settings,'enforcing',1)==1
        guarded=i>0 and entries[i-1]['module']=='pam_localuser.so' and entries[i-1]['control']=='[success=ok default=1]'
        remembered=integer(settings,'remember',10)
        return guarded and remembered is not None and remembered>=5 and settings.get('use_authtok') is True
    if issue==9:
        if any(not evaluate(9,service) for service in d.get('services',[])): return False
        auth=[e for e in stack(d.get('auth','')) if e['type']=='auth']
        account=[e for e in stack(d.get('account','')) if e['type']=='account']
        # Accept only the rehearsed Unix/SSSD branch semantics, with optional
        # non-branching service guards. Presence of faillock is insufficient.
        core=[('pam_localuser.so','[success=ok default=1]'),('pam_faillock.so','required'),
              ('pam_unix.so','[success=3 default=ignore]'),('pam_sss.so','[success=2 default=ignore]'),
              ('pam_faillock.so','[default=die]'),('pam_deny.so','requisite'),
              ('pam_faillock.so','required'),('pam_permit.so','required')]
        start=next((i for i,e in enumerate(auth) if e['module']=='pam_localuser.so'),None)
        if start is None or [(e['module'],e['control']) for e in auth[start:start+8]]!=core: return False
        safe_extras={'pam_faildelay.so','pam_nologin.so','pam_group.so','pam_cap.so'}
        if any(e['module'] not in safe_extras or e['control'] not in ('required','requisite','optional')
               for e in auth[:start]+auth[start+8:]): return False
        first_lock=next((i for i,e in enumerate(account) if e['module']=='pam_faillock.so'),None)
        if first_lock is None or any(e['control'] not in ('required','requisite','optional') for e in account[:first_lock]): return False
        locks=[e for e in auth if e['module']=='pam_faillock.so']
        phases=[next((e for e in locks if phase in e['args']),None) for phase in ('preauth','authfail','authsucc')]
        if any(e is None for e in phases): return False
        if phases[0]['control'] not in ('required','requisite') or phases[1]['control']!='[default=die]': return False
        if not any(e['module']=='pam_faillock.so' and e['control']=='required' for e in account): return False
        unix=next((i for i,e in enumerate(auth) if e['module']=='pam_unix.so'),None)
        if unix is None or auth.index(phases[0])>=unix or auth.index(phases[1])<=unix: return False
        for e in phases:
            if 'conf' in e['args']: return False
            settings={**d.get('faillock',{}),**e['args']}
            if (integer(settings,'deny',3)!=5 or integer(settings,'fail_interval',900)!=900 or
                integer(settings,'unlock_time',600)!=900 or settings.get('local_users_only') is not True or
                settings.get('even_deny_root') is True): return False
        # Exact branch behavior is still proved with disposable local and AD
        # authentication during staging; this parser is not a PAM interpreter.
        return True
    return False

def expanded(name,depth=0):
    if depth>8: raise ProbeError('PAM include recursion')
    p=Path('/etc/pam.d')/name
    if p.parent != Path('/etc/pam.d'): raise ProbeError('Unsafe PAM include')
    output=[]
    for raw in read(p).splitlines():
        line=raw.split('#',1)[0].strip()
        if line.startswith('@include '): output.append(expanded(line.split()[1],depth+1))
        elif re.match(r'\S+\s+(include|substack)\s+',line):
            parts=line.split(); output.append(expanded(parts[2],depth+1))
        else: output.append(raw)
    return '\n'.join(output)

def optional_config(path): return policy(read(path)) if Path(path).is_file() else {}

def collect(issue):
    d={'password':expanded('common-password'),'auth':expanded('common-auth'),'account':expanded('common-account')}
    quality={}
    for p in sorted(Path('/etc/security/pwquality.conf.d').glob('*.conf')): quality.update(policy(read(p)))
    quality.update(optional_config('/etc/security/pwquality.conf'))
    d.update(quality=quality,history=optional_config('/etc/security/pwhistory.conf'),faillock=optional_config('/etc/security/faillock.conf'))
    if issue==9:
        d['services']=[{'auth':expanded(name),'account':expanded(name),'faillock':d['faillock']}
                       for name in ('sshd','login')]
    # Honor per-module alternate configuration paths when explicitly selected.
    for key,text,module in [('quality',d['password'],'pam_pwquality.so'),('history',d['password'],'pam_pwhistory.so')]:
        matches=[e for e in stack(text) if e['module']==module]
        if len(matches)==1 and 'conf' in matches[0]['args']: d[key]=policy(read(matches[0]['args']['conf']))
    return d

def check(issue): return evaluate(issue,collect(issue))
