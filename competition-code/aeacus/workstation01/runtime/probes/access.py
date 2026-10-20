#!/usr/bin/env python3
"""Conservative effective access probes for the fixed AlmaLinux scenario."""
import argparse
import configparser
import json
from pathlib import Path
import re
import shlex
from policy import run, secure_file
from scenario import text_read

ISSUES=(1,2,3,4,7,8,15,20,21,22,26,31,39,40)
COMPETITOR_ADMINS=('alex.admin@corp.summit.test','taylor.admin@corp.summit.test')
SSH_GROUPS={'jwang','competitor-recovery','linux-workstation-admins@corp.summit.test'}
SSH_USERS=('root','jwang','competitor-recovery')+COMPETITOR_ADMINS+('summit-unknown','summit-employee')


def settings(texts):
    result={}
    for text in texts:
        if not isinstance(text,str):
            return None
        for raw in text.splitlines():
            line=raw.split('#',1)[0].strip()
            if not line:
                continue
            if not re.fullmatch(r'[\w]+(?:\s*=\s*[^\s]+)?',line):
                return None
            k,sep,v=line.partition('=')
            result[k.strip()]=v.strip() if sep else '1'
    return result


def pam_line(text,kind,module):
    if not isinstance(text,str):
        return None
    matches=[]
    earlier=[]
    for raw in text.splitlines():
        fields=raw.split('#',1)[0].split()
        if not fields or fields[0]!=kind:
            continue
        if len(fields)<3:
            return None
        if fields[2]==module:
            if fields[1] not in ('required','requisite') or any('sufficient' in f or 'pam_permit.so' in f for f in earlier):
                return None
            args={}
            for arg in fields[3:]:
                key,sep,value=arg.partition('=')
                args[key]=value if sep else '1'
            matches.append(args)
        else:
            earlier.append(fields)
    return matches[0] if len(matches)==1 else None


def password_ok(issue,args,cfg):
    if args is None or cfg is None or args.get('local_users_only')!='1' or 'conf' in args:
        return False
    effective=dict(minlen='8',enforcing='1',dcredit='0',ucredit='0',lcredit='0',ocredit='0',dictcheck='1',usercheck='1')
    effective.update(cfg)
    effective.update(args)
    try:
        if issue==1:
            credits=sum(max(0,int(effective[k])) for k in ('dcredit','ucredit','lcredit','ocredit'))
            return effective['enforcing']=='1' and int(effective['minlen'])-credits>=14
        return effective['enforcing']=='1' and effective['dictcheck']=='1' and effective['usercheck']=='1'
    except (ValueError,KeyError):
        return False


def ssh_output_rows(text):
    if not isinstance(text,str):
        return None
    rows={}
    for line in text.splitlines():
        fields=line.split()
        if fields:
            rows.setdefault(fields[0],[]).extend(fields[1:])
    return rows


def ssh_allowed(text,organizer):
    rows=ssh_output_rows(text)
    if rows is None or not organizer:
        return False
    groups=rows.get('allowgroups',[])
    return len(groups)==len(SSH_GROUPS) and set(groups)==SSH_GROUPS and not rows.get('allowusers') and not rows.get('denyusers') and not rows.get('denygroups')


def sudo_denied(code,stdout,stderr,name):
    # sudo 1.9.17p2 can return success for a completed policy lookup which
    # explicitly denies authorization. Command success alone is not denial.
    expected='User %s is not allowed to run sudo on workstation01.'%name
    return code in (0,1) and isinstance(stdout,str) and isinstance(stderr,str) and (stdout+'\n'+stderr).strip()==expected


def sudo_safe(text,issue):
    if not isinstance(text,str) or 'Sudoers entry:' not in text:
        return False
    blocks=text.split('Sudoers entry:')[1:]
    if not blocks or any('Commands:' not in b for b in blocks):
        return False
    # Root resolves aliases, group membership and included policy via sudo -ll.
    if issue==20:
        return all(not re.search(r'!authenticate|NOPASSWD|!rootpw|exempt_group',b) for b in blocks) and not re.search(r'!authenticate|exempt_group\s*=',text.split('Sudoers entry:')[0])
    values=re.findall(r'timestamp_timeout\s*=\s*(-?\d+(?:\.\d+)?)',text)
    # Installed sudo default is 5 min, but require scenario's explicit policy.
    return bool(values) and all(0<=float(v)<=5 for v in values)


def competitor_sudo_ok(listings,issue):
    return issue in (20,21) and all(sudo_safe(listings.get(name),issue) for name in COMPETITOR_ADMINS)


def firewall_safe(data):
    required={'target','services','ports','rich_rules','forward_ports','sources','protocols'}
    return required<=data.keys() and data['target'] in ('default','DROP','REJECT','%%REJECT%%') and 'ssh' in data['services'] and set(data['services'])<= {'ssh','dhcpv6-client'} and all(data[k]==[] for k in ('ports','rich_rules','forward_ports','sources','protocols'))


def successful(argv):
    p=run(argv)
    return p.stdout.strip() if p is not None and p.returncode==0 else None


def unit_ready(name):
    text=successful(['systemctl','show',name,'-p','ActiveState','-p','UnitFileState','-p','LoadState'])
    if text is None:
        return False
    values=dict(l.split('=',1) for l in text.splitlines() if '=' in l)
    return values.get('LoadState')=='loaded' and values.get('ActiveState')=='active' and values.get('UnitFileState')=='enabled'


def pam_ok():
    p=run(['authselect','check'])
    current=successful(['authselect','current','-r'])
    return p is not None and p.returncode==0 and current is not None and ('sssd' in current or current.startswith('custom/')) and 'with-mkhomedir' in current


def auth_check(issue):
    if not pam_ok():
        return False
    stacks=[text_read('/etc/pam.d/system-auth'),text_read('/etc/pam.d/password-auth')]
    if any(s is None or 'pam_sss.so' not in s for s in stacks):
        return False
    if issue in (1,2):
        paths=sorted(Path('/etc/security/pwquality.conf.d').glob('*.conf'))+[Path('/etc/security/pwquality.conf')]
        cfg=settings([text_read(p) for p in paths])
        return all(password_ok(issue,pam_line(s,'password','pam_pwquality.so'),cfg) for s in stacks)
    if issue==3:
        cfg=settings([text_read('/etc/security/faillock.conf')])
        if cfg is None:
            return False
        for stack in stacks:
            lines=[l.split('#',1)[0] for l in stack.splitlines() if 'pam_faillock.so' in l and not l.lstrip().startswith('#')]
            if not any('preauth' in l and 'required' in l for l in lines) or not any('authfail' in l for l in lines) or not any(l.startswith('account') and 'required' in l for l in lines):
                return False
            for line in lines:
                args=settings([a.replace('=', ' = ',1) for a in line.split()[line.split().index('pam_faillock.so')+1:]])
                if args is None or 'conf' in args:
                    return False
                effective=dict(deny='3',fail_interval='900',unlock_time='600')
                effective.update(cfg); effective.update(args)
                if any(effective.get(k)!=v for k,v in {'deny':'5','fail_interval':'900','unlock_time':'900','local_users_only':'1'}.items()):
                    return False
        return True
    cfg=settings([text_read('/etc/security/pwhistory.conf')])
    if cfg is None:
        return False
    for stack in stacks:
        args=pam_line(stack,'password','pam_pwhistory.so')
        # SSSD template uses pam_localuser to skip pwhistory for domain users.
        prefix=stack.split('pam_pwhistory.so',1)[0]
        if args is None or 'pam_localuser.so' not in prefix or args.get('use_authtok')!='1' or 'conf' in args:
            return False
        try:
            if int(args.get('remember',cfg.get('remember','10')))<5:
                return False
        except ValueError:
            return False
    return True


def summary_field(text,key):
    if not isinstance(text,str): return None
    values=re.findall(r'^[ \t]+'+re.escape(key)+r':[ \t]*([^\r\n]*)$',text,re.M)
    return values[0].strip() if len(values)==1 else None


def firewall_check():
    if not unit_ready('firewalld.service'):
        return False
    for permanent in (False,True):
        prefix=['firewall-cmd']+(['--permanent'] if permanent else [])
        zone=successful(prefix+['--get-zone-of-interface=enp6s18'])
        if zone is None or not re.fullmatch(r'[\w-]+',zone):
            return False
        zones=successful(prefix+['--get-zones'])
        if zones is None: return False
        for name in zones.split():
            sources=successful(prefix+['--zone='+name,'--list-sources'])
            interfaces=successful(prefix+['--zone='+name,'--list-interfaces'])
            if sources is None or sources or interfaces is None: return False
            if name!=zone and any(i!='lo' for i in interfaces.split()): return False
        query=prefix+['--zone='+zone]
        summary=successful(query+['--list-all'])
        data={}
        for key,option in {'target':'--get-target','services':'--list-services','ports':'--list-ports','rich_rules':'--list-rich-rules','forward_ports':'--list-forward-ports','sources':'--list-sources','protocols':'--list-protocols'}.items():
            value=summary_field(summary,'target') if key=='target' else successful(query+[option])
            if value is None:
                return False
            data[key]=value if key=='target' else value.splitlines() if key in ('rich_rules','forward_ports') else value.split()
        if not firewall_safe(data):
            return False
        # Direct rules and policies may accept traffic outside zone filtering.
        direct=successful(prefix+['--direct','--get-all-rules'])
        policies=successful(prefix+['--get-policies'])
        if direct is None or direct or policies is None:
            return False
        for name in policies.split():
            # Built-in allow-host-ipv6 has only required IPv6 control traffic.
            if name!='allow-host-ipv6':
                return False
            q=prefix+['--policy='+name]
            info=successful(q+['--list-all'])
            if summary_field(info,'target')!='CONTINUE' or summary_field(info,'priority')!='-15000': return False
            required={'--list-ingress-zones':'ANY','--list-egress-zones':'HOST','--list-services':'','--list-ports':'','--list-protocols':'','--list-forward-ports':''}
            if any(successful(q+[key])!=value for key,value in required.items()): return False
            rules=successful(q+['--list-rich-rules'])
            expected={'rule family="ipv6" icmp-type name="'+kind+'" accept' for kind in ('neighbour-advertisement','neighbour-solicitation','router-advertisement','redirect','mld-listener-done','mld-listener-query','mld-listener-report','mld2-listener-report')}
            if rules is None or set(rules.splitlines())!=expected: return False
    return True


def check(issue):
    if issue in (1,2,3,4):
        return auth_check(issue)
    if issue==7:
        outputs=[successful(['/usr/sbin/sshd','-T','-C','user=%s,host=workstation01,addr=%s'%(user,addr)]) for user in SSH_USERS for addr in ('10.77.10.50','10.77.20.20')]
        if not all(ssh_allowed(o,True) for o in outputs):
            return False
        for user in SSH_USERS:
            groups=successful(['id','-nG',user])
            if groups is None or bool(set(groups.split()) & SSH_GROUPS)!=(user in ('jwang','competitor-recovery')+COMPETITOR_ADMINS):
                return False
        return True
    if issue==8:
        p=run(['getent','-s','files','passwd','summit-keyuser'])
        if p is None or p.returncode!=0:
            return False
        try:
            fields=p.stdout.strip().split(':'); uid=int(fields[2]); home=Path(fields[5]); directory=home/'.ssh'; key=directory/'authorized_keys'
            for path,mode in ((directory,0o700),(key,0o600)):
                s=path.lstat()
                if path.is_symlink() or s.st_uid!=uid or s.st_mode & 0o7777!=mode:
                    return False
                acl=successful(['getfacl','-cp',str(path)])
                if acl is None or re.search(r'^(?:default:)?(?:user|group):[^:]+:',acl,re.M):
                    return False
            return key.is_file() and bool(key.read_text().strip())
        except (OSError,ValueError,IndexError):
            return False
    if issue==15:
        return firewall_check()
    if issue in (20,21):
        listings={name:successful(['sudo','-n','-ll','-U',name]) for name in COMPETITOR_ADMINS}
        return competitor_sudo_ok(listings,issue)
    if issue in (39,40):
        name='summit-employee' if issue==39 else 'summit-auditor'
        user=successful(['getent','-s','files','passwd',name])
        if user is None:
            return False
        p=run(['sudo','-n','-ll','-U',name])
        if p is None or not sudo_denied(p.returncode,p.stdout,p.stderr,name):
            return False
        groups=successful(['id','-nG',name])
        return groups is not None and 'wheel' not in groups.split()
    if issue==22:
        if not unit_ready('auditd.service'):
            return False
        status=successful(['auditctl','-s']); rules=successful(['auditctl','-l'])
        if status is None or rules is None or not re.search(r'^enabled\s+[12]$',status,re.M):
            return False
        # Exact standard account-file watches; live kernel rules plus boot files.
        boot='\n'.join(text_read(p) or '' for p in Path('/etc/audit/rules.d').glob('*.rules'))
        required=['/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow','/etc/sudoers']
        return all(any('-w '+path+' ' in l and re.search(r'-p\s+(?:wa|aw)(?:\s|$)',l) and '-k summit-identity' in l for l in rules.splitlines()) and any('-w '+path+' ' in l and '-k summit-identity' in l and re.search(r'-p\s+(?:wa|aw)(?:\s|$)',l) for l in boot.splitlines() if not l.lstrip().startswith('#')) for path in required)
    if issue==26:
        text=text_read('/etc/dnf/automatic.conf')
        if text is None:
            return False
        try:
            cfg=configparser.ConfigParser(interpolation=None); cfg.read_string(text)
            return cfg.get('commands','upgrade_type')=='security' and cfg.getboolean('commands','apply_updates') and cfg.getboolean('commands','download_updates') and unit_ready('dnf-automatic-install.timer')
        except (configparser.Error,ValueError):
            return False
    if issue==31:
        # Require a machine-wide locked policy, so local and domain sessions
        # share the rule and per-user overrides cannot disable it.
        profile=text_read('/etc/dconf/profile/user')
        if profile is None or 'system-db:local' not in profile.splitlines():
            return False
        keys=[('org.gnome.desktop.screensaver','lock-enabled'),('org.gnome.desktop.screensaver','lock-delay'),('org.gnome.desktop.session','idle-delay')]
        values=[]
        for schema,key in keys:
            if successful(['gsettings','writable',schema,key])!='false':
                return False
            values.append(successful(['gsettings','get',schema,key]))
        try:
            delay=int((values[1] or '').replace('uint32 ','')); idle=int((values[2] or '').replace('uint32 ',''))
            return values[0]=='true' and 0<idle<=300 and 0<=delay and idle+delay<=300
        except ValueError:
            return False
    return False


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--issue',type=int,choices=ISSUES)
    parser.add_argument('--report',action='store_true')
    args=parser.parse_args()
    if args.report:
        print(json.dumps({str(i):{'pass':check(i)} for i in ISSUES},indent=2))
    elif args.issue is not None:
        print('PASS' if check(args.issue) else 'FAIL')
    else:
        parser.error('Specify --issue or --report')
