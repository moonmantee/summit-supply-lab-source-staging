#!/usr/bin/env python3
"""Read-only effective-state checks. Exceptions are ERROR, never FAIL/PASS."""
import hashlib,json,os,pathlib,re,subprocess,sys
from contract import answer,backup_acl_ok,parse_native,unit_safe
ROOT=pathlib.Path('/opt/summit-sql01')
PUBLIC=pathlib.Path('/srv/summit-sql01')

def run(args):
    p=subprocess.run(args,text=True,capture_output=True,timeout=20)
    if p.returncode: raise RuntimeError(args[0]+' exit '+str(p.returncode)+': '+p.stderr[-300:])
    return p.stdout

def sql(query): return run(['mariadb','--batch','--skip-column-names','-e',query]).strip()

def unit(name):
    lines=run(['systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','UnitFileState'])
    result=dict(line.split('=',1) for line in lines.splitlines() if '=' in line)
    if result.get('LoadState')=='not-found': raise RuntimeError('Missing required baseline unit '+name)
    return result

def ssh_setting(key,value):
    run(['/usr/sbin/sshd','-t'])
    contexts=('jwang','root','alex.admin@corp.summit.test','taylor.admin@corp.summit.test')
    for user in contexts:
        data=parse_native(run(['/usr/sbin/sshd','-T','-C','user='+user+',host=sql01,addr=10.77.50.1']))
        if key not in data: raise RuntimeError('Missing ssh option')
        if data[key]!=[value]: return False
    return True

def privilege_free(name):
    p=subprocess.run(['sudo','-l','-U',name],text=True,capture_output=True,timeout=20)
    if p.returncode not in (0,1): raise RuntimeError('sudo enumeration failed')
    if p.returncode==1:
        if 'not allowed to run sudo' in p.stderr+p.stdout: return True
        raise RuntimeError('Cannot resolve sudo identity')
    # Baseline Mint maintenance commands are permitted; all other grants are excess.
    grants=[line.strip() for line in p.stdout.splitlines() if line.strip().startswith('(')]
    allowed={'(root) NOPASSWD: /usr/bin/mintdrivers-remove-live-media',
             '(root) NOPASSWD: /usr/bin/mintdrivers-load-broadcom-modules',
             '(root) NOPASSWD: /usr/bin/mint-refresh-cache',
             '(root) NOPASSWD: /usr/lib/linuxmint/mintUpdate/dpkg_lock_check.sh'}
    return all(g in allowed for g in grants)

def effective_grantees(user,host):
    # Follow inherited MariaDB roles; revoking a direct grant must not hide an equivalent role grant.
    rows=sql('SELECT User,Host,Role FROM mysql.roles_mapping;')
    pending=[(user,host)]; visited=set()
    while pending:
        principal=pending.pop()
        if principal in visited: continue
        visited.add(principal)
        for line in rows.splitlines():
            u,h,role=line.split('\t')
            if (u,h)==principal: pending.append((role,''))
    def literal(s): return "'"+s.replace('\\','\\\\').replace("'","\\'")+"'"
    return ','.join(literal("'"+u+"'@'"+h+"'") for u,h in visited)

def scope_absent(marker):
    homes=[pathlib.Path('/home/jwang'),pathlib.Path('/home/alex.admin@corp.summit.test'),pathlib.Path('/home/taylor.admin@corp.summit.test')]
    for base in [PUBLIC/'shared']+homes:
        if not base.exists(): continue
        for directory,dirs,files in os.walk(base,followlinks=False,onerror=lambda e: (_ for _ in ()).throw(e)):
            dirs[:]=[d for d in dirs if d not in ('.cache','.mozilla','.local')]
            for name in files:
                p=pathlib.Path(directory)/name
                if p.is_symlink():
                    resolved=p.resolve(strict=True)
                    if not any(resolved.is_relative_to(h) for h in homes+[PUBLIC/'shared']): continue
                if not p.is_file(): continue
                # Bounded memory reads, including renamed copies and large files.
                with p.open('rb') as f:
                    tail=b''
                    while True:
                        block=f.read(65536)
                        if not block: break
                        if marker in tail+block: return False
                        tail=block[-len(marker):]
    return True

def check(number,answer_root=None):
    # Removing a business dependency must never manufacture remediation credit.
    for name in ('mariadb','ssh','sssd'):
        if unit(name)['ActiveState']!='active': raise RuntimeError('Business dependency inactive: '+name)
    for user,host,db in (('shop_app','10.77.30.10','summit_shop'),('forum_app','10.77.30.20','forum')):
        exists=sql("SELECT COUNT(*) FROM mysql.user WHERE User='"+user+"' AND Host='"+host+"';")
        rights=set(sql("SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=\"'"+user+"'@'"+host+"'\" AND TABLE_SCHEMA='"+db+"';").splitlines())
        if exists!='1' or not {'SELECT','INSERT','UPDATE','DELETE'}<=rights:
            raise RuntimeError('Required application identity/rights missing')
    metadata=json.loads((ROOT/'metadata.json').read_text())
    if number==1:
        live=sql("SELECT @@GLOBAL.local_infile;")
        help_text=run(['mariadbd','--verbose','--help'])
        matches=re.findall(r'^local-infile\s+(\S+)\s*$',help_text,re.M)
        if len(matches)!=1: raise RuntimeError('Persistent local-infile unavailable')
        return live=='0' and matches[0].lower() in ('false','off','0')
    if number==2: return sql("SELECT COUNT(*) FROM mysql.user WHERE User='training_vendor';")=='0'
    if number==3:
        names=effective_grantees('shop_app','10.77.30.10')
        rows=sql('SELECT PRIVILEGE_TYPE FROM information_schema.USER_PRIVILEGES WHERE GRANTEE IN ('+names+');').splitlines()
        return 'FILE' not in rows
    if number==4:
        names=effective_grantees('forum_app','10.77.30.20')
        rows=sql("SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE IN ("+names+") AND 'summit_shop' LIKE TABLE_SCHEMA;")
        tables=sql("SELECT PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE IN ("+names+") AND TABLE_SCHEMA='summit_shop';")
        global_rows=sql("SELECT PRIVILEGE_TYPE FROM information_schema.USER_PRIVILEGES WHERE GRANTEE IN ("+names+") AND PRIVILEGE_TYPE IN ('SELECT','SUPER');")
        return not rows and not tables and not global_rows
    if number in (5,6,7): return ssh_setting({5:'permitrootlogin',6:'permitemptypasswords',7:'x11forwarding'}[number],'no')
    if number in (8,9): return privilege_free({8:'summit_employee',9:'summit_contractor'}[number])
    if number==10:
        p=PUBLIC/'operations/catalog-backup.txt'
        s=p.stat()
        acl=run(['getfacl','-cp',str(p)])
        good=hashlib.sha256(p.read_bytes()).hexdigest()==metadata['backup_hash']
        return backup_acl_ok(s.st_uid,s.st_mode & 0o7777,acl,good,s.st_gid)
    if number==11:
        payload='/usr/local/lib/summit-sql01/cron-marker.py'
        for base in ('/etc/crontab','/etc/cron.d','/var/spool/cron/crontabs'):
            p=pathlib.Path(base)
            files=[p] if p.is_file() else list(p.glob('*')) if p.is_dir() else []
            for f in files:
                if f.is_file():
                    for line in f.read_text().splitlines():
                        if not line.lstrip().startswith('#') and payload in line: return False
        return not pathlib.Path(payload).exists()
    if number==12:
        for name in ('summit-sql01-marker.timer','summit-sql01-marker.service'):
            state=dict(line.split('=',1) for line in run(['systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','UnitFileState']).splitlines() if '=' in line)
            if state.get('LoadState')!='not-found' and not unit_safe(state): return False
        return not pathlib.Path('/usr/local/lib/summit-sql01/timer-marker.py').exists()
    if number in (13,14): return scope_absent(metadata[{13:'credential_marker',14:'media_marker'}[number]].encode())
    if number in (15,16):
        names={15:('avahi-daemon.service','avahi-daemon.socket'),16:('cups.service','cups.socket','cups.path')}[number]
        return all(unit_safe(unit(n)) for n in names)
    if number==17:
        config=run(['systemd-analyze','cat-config','systemd/journald.conf'])
        storage='auto'; section=''
        for line in config.splitlines():
            line=line.strip()
            if not line or line.startswith(('#',';')): continue
            if line.startswith('['): section=line
            elif section=='[Journal]' and '=' in line:
                k,v=line.split('=',1)
                if k.strip()=='Storage': storage=v.strip()
        pid=run(['systemctl','show','systemd-journald','-p','MainPID','--value']).strip()
        if not pid.isdigit() or pid=='0': raise RuntimeError('Journald PID unavailable')
        paths=[os.readlink(p) for p in pathlib.Path('/proc/'+pid+'/fd').iterdir()]
        return storage=='persistent' and any(p.startswith('/var/log/journal/') and p.endswith('.journal') for p in paths)
    if number in (18,19,20,21,22):
        options={18:('maxauthtries','3'),19:('allowagentforwarding','no'),20:('allowtcpforwarding','no'),21:('permituserenvironment','no'),22:('loglevel','VERBOSE')}
        key,value=options[number]
        if number==18:
            run(['/usr/sbin/sshd','-t'])
            for user in ('jwang','root','alex.admin@corp.summit.test','taylor.admin@corp.summit.test'):
                values=parse_native(run(['/usr/sbin/sshd','-T','-C','user='+user+',host=sql01,addr=10.77.50.1']))['maxauthtries']
                if len(values)!=1 or not 1<=int(values[0])<=3: return False
            return True
        return ssh_setting(key,value)
    if number in (23,24,25,26):
        keys={23:'fs.protected_hardlinks',24:'fs.protected_symlinks',25:'kernel.kptr_restrict',26:'kernel.dmesg_restrict'}
        key=keys[number]
        live=int(run(['sysctl','-n',key]).strip())
        text=run(['/usr/lib/systemd/systemd-sysctl','--cat-config'])
        effective=None
        for line in text.splitlines():
            line=line.strip()
            if not line or line.startswith(('#',';')) or '=' not in line: continue
            k,v=line.split('=',1)
            if k.strip().lstrip('-').replace('/','.')==key: effective=int(v.strip())
        if effective is None: raise RuntimeError('Persistent sysctl setting unreadable')
        return live>=1 and effective>=1
    if number==27:
        p=pathlib.Path('/etc/profile.d/summit-sql01-training.sh'); s=p.stat()
        acl=run(['getfacl','-cp',str(p)])
        if hashlib.sha256(p.read_bytes()).hexdigest()!=metadata['profile_hash']: return False
        if s.st_uid!=0 or s.st_mode & 0o022: return False
        for line in acl.splitlines():
            parts=line.split('#',1)[0].strip().split(':')
            if len(parts)==3 and parts[0] in ('user','group') and parts[1] and 'w' in parts[2]: return False
        return True
    if number in (28,29,30):
        base=pathlib.Path(answer_root) if answer_root else PUBLIC/'questions'
        text=(base/('Question-'+str(number-27)+'.txt')).read_text()
        return answer(text)==metadata['answers'][str(number-27)].casefold()
    raise ValueError('Unknown objective')

def verdict(number,answer_root=None):
    try: return 'PASS' if check(number,answer_root) else 'FAIL'
    except Exception as e:
        print(str(e),file=sys.stderr)
        return 'ERROR'

if __name__=='__main__':
    result=verdict(int(sys.argv[1]))
    print(result)
    sys.exit(2 if result=='ERROR' else 0)
