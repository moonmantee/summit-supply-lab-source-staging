"""Runtime plus persistent host-defense checks with conservative parsing."""
import json
import ipaddress
import re
import shlex
from pathlib import Path
from common import ProbeError, active, read, result, run, setting, unit

ISSUES=tuple(range(17,25))
PROFILE='rsyslogd'
WATCHES={'/etc/passwd','/etc/group','/etc/shadow','/etc/sudoers','/etc/sudoers.d'}
SSH_SOURCES={'10.77.10.50/32','10.77.10.1/32','10.77.30.1/32','10.77.70.10/32'}

def inactive_firewall_baseline(text,ipv6=False):
    """Accept an empty table or inactive standard UFW hooks, never real rules."""
    prefix='ufw6' if ipv6 else 'ufw'
    builtins={'INPUT','FORWARD','OUTPUT'}
    suffixes=('before-logging','before','after','after-logging','reject','track')
    hooks={prefix+'-'+suffix+'-'+name.lower() for name in builtins for suffix in suffixes}
    declarations={}; rules=[]; tables=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or line=='COMMIT': continue
        if line.startswith('*'): tables.append(line); continue
        if line.startswith(':'):
            parts=line[1:].split()
            if len(parts)!=3: return False
            declarations[parts[0]]=parts[1]; continue
        if line.startswith('-A '): rules.append(shlex.split(line)); continue
        return False
    if not tables: return not declarations and not rules
    if tables!=['*filter'] or not all(declarations.get(n)=='ACCEPT' for n in builtins): return False
    if any(name not in builtins and (name not in hooks or policy!='-') for name,policy in declarations.items()): return False
    for rule in rules:
        if len(rule)!=4 or rule[1] not in builtins or rule[2]!='-j': return False
        if rule[3] not in declarations or rule[3] not in {prefix+'-'+s+'-'+rule[1].lower() for s in suffixes}: return False
    return True

def normalized_user_rules(text,ipv6=False):
    """Normalize only audited TCP rule syntax; keep rule ordering/constraints."""
    chain=('ufw6' if ipv6 else 'ufw')+'-user-input'
    normalized=[]
    for line in text.splitlines():
        if not line.startswith('-A '+chain+' '): continue
        tokens=shlex.split(line)[2:]; options={}
        if len(tokens)%2: return None
        for i in range(0,len(tokens),2):
            key,value=tokens[i:i+2]
            if key not in ('-s','-d','-p','-m','--dport','-j') or key in options: return None
            options[key]=value
        if options.get('-p')!='tcp' or options.get('-m','tcp')!='tcp': return None
        if options.get('-j') not in ('ACCEPT','DROP','REJECT'): return None
        if not options.get('--dport','').isdigit() or not 1<=int(options['--dport'])<=65535: return None
        default='::/0' if ipv6 else '0.0.0.0/0'
        try:
            source=ipaddress.ip_network(options.get('-s',default),strict=False)
            destination=ipaddress.ip_network(options.get('-d',default),strict=False)
        except ValueError: return None
        if source.version!=(6 if ipv6 else 4) or destination.version!=source.version: return None
        normalized.append((str(source),str(destination),'tcp',int(options['--dport']),options['-j']))
    return normalized

def persistent_rules_match(live,saved,ipv6=False):
    a=normalized_user_rules(live,ipv6); b=normalized_user_rules(saved,ipv6)
    return a is not None and b is not None and a==b


def persistent_auxiliary_match(live,saved,ipv6=False):
    prefix='ufw6' if ipv6 else 'ufw'
    # Compare every saved input-reachable helper chain, preserving rule order.
    chains={m[1] for l in saved.splitlines() if (m:=re.match(r'^:([^ ]+) ',l))}
    wanted={c for c in chains if c.endswith('-input') or c==prefix+'-not-local'}
    def parsed(text):
        output={c:[] for c in wanted}
        aliases={'destination-unreachable':'3','time-exceeded':'11','parameter-problem':'12','echo-request':'8',
                 'packet-too-big':'2','neighbor-solicitation':'135','neighbor-advertisement':'136',
                 'router-solicitation':'133','router-advertisement':'134'}
        if ipv6: aliases.update({'destination-unreachable':'1','time-exceeded':'3','parameter-problem':'4','echo-request':'128','echo-reply':'129'})
        for line in text.splitlines():
            if not line.startswith('-A '): continue
            t=shlex.split(line); chain=t[1]
            if chain not in wanted: continue
            if t==['-A',prefix+'-before-input','-j',prefix+'-user-input']: continue
            if len(t[2:])%2: return None
            options=[]
            for i in range(2,len(t),2):
                key,value=t[i:i+2]
                if key=='-m' and value in ('tcp','udp','icmp','icmp6','ipv6-icmp'): continue
                if key=='-p' and value=='icmpv6': value='ipv6-icmp'
                if key in ('--icmp-type','--icmpv6-type'): value=aliases.get(value,value)
                if key=='--ctstate': value=','.join(sorted(value.split(',')))
                if key in ('-s','-d'):
                    try: value=str(ipaddress.ip_network(value,strict=False))
                    except ValueError: return None
                if key=='--limit': value=value.replace('/minute','/min').replace('/second','/sec')
                options.append((key,value))
            output[chain].append(sorted(options))
        return output
    a=parsed(live); b=parsed(saved)
    return a is not None and a==b

def watches(text):
    found=set()
    for line in text.splitlines():
        t=shlex.split(line)
        if '-w' in t and '-p' in t:
            path=t[t.index('-w')+1]; perms=t[t.index('-p')+1]
            if 'w' in perms and 'a' in perms: found.add(path.rstrip('/'))
    return found

def journal_storage(text):
    storage=None; section=None
    for raw in text.splitlines():
        line=raw.split('#',1)[0].strip()
        if line.startswith('['): section=line
        elif section=='[Journal]' and line.startswith('Storage='): storage=line.split('=',1)[1].strip()
    return storage

def firewall_rules_safe(text,ipv6=False):
    prefix='ufw6' if ipv6 else 'ufw'
    user_input=prefix+'-user-input'
    if not re.search(r'(?m)^:INPUT DROP ',text): return False
    allowed=set()
    chains={}
    for line in text.splitlines():
        if line.startswith(':'):
            chains.setdefault(line[1:].split()[0],[])
        elif line.startswith('-A '):
            rule=shlex.split(line); chains.setdefault(rule[1],[]).append(rule)
    def option(rule,flag):
        if flag not in rule or rule.count(flag)!=1: return None
        pos=rule.index(flag)
        return rule[pos+1] if pos+1<len(rule) else None
    reachable=set(); pending=['INPUT']
    terminals={'ACCEPT','DROP','REJECT','RETURN','LOG','NFLOG'}
    while pending:
        chain=pending.pop()
        if chain in reachable: continue
        reachable.add(chain)
        for rule in chains.get(chain,[]):
            target=option(rule,'-j') or option(rule,'-g')
            if not target: return False
            if target not in terminals:
                if target not in chains: return False
                pending.append(target)
            elif target=='ACCEPT' and chain!=user_input:
                if '!' in rule: return False
                if option(rule,'-i')=='lo': continue
                states=option(rule,'--ctstate')
                if states and set(states.split(',')) <= {'RELATED','ESTABLISHED'}: continue
                proto=option(rule,'-p')
                kind=option(rule,'--icmp-type') or option(rule,'--icmpv6-type')
                control={'destination-unreachable','packet-too-big','time-exceeded','parameter-problem','echo-request','echo-reply',
                         'neighbor-solicitation','neighbor-advertisement','router-solicitation','router-advertisement',
                         '1','2','3','4','8','11','12','128','129','130','131','132','133','134','135','136','137',
                         '141','142','143','144','145','146','147','148','149','151','152','153'}
                if proto in ('icmp','ipv6-icmp','icmpv6') and kind in control: continue
                if proto=='udp' and (option(rule,'--sport'),option(rule,'--dport')) in (('67','68'),('547','546')): continue
                return False
    known_input={prefix+'-'+suffix for suffix in ('before-logging-input','before-input','after-input','after-logging-input','reject-input','track-input')}
    for line in text.splitlines():
        if not line.startswith('-A '): continue
        t=shlex.split(line); chain=t[1]
        if chain=='INPUT':
            if len(t)!=4 or t[2]!='-j' or t[3] not in known_input: return False
        if chain!=user_input: continue
        if '-j' not in t: return False
        target=t[t.index('-j')+1]
        if target in ('DROP','REJECT'): continue
        if target!='ACCEPT' or '-p' not in t or t[t.index('-p')+1]!='tcp' or '--dport' not in t: return False
        port=t[t.index('--dport')+1]; src=t[t.index('-s')+1] if '-s' in t else ('::/0' if ipv6 else '0.0.0.0/0')
        # Unknown match/target clauses require separate audit rather than credit.
        if any(flag in t for flag in ('!','--sports','--dports','-i','-o')): return False
        if port=='22' and not ipv6 and src in SSH_SOURCES: allowed.add((port,src))
        elif port in ('80','443') and src in ('0.0.0.0/0','::/0'): allowed.add((port,src))
        else: return False
    required={('80','::/0' if ipv6 else '0.0.0.0/0'),('443','::/0' if ipv6 else '0.0.0.0/0')}
    if not ipv6: required.update(('22',s) for s in SSH_SOURCES)
    if user_input not in reachable or not required<=allowed: return False
    return all(tcp_flow_allowed(chains,source.split('/')[0],int(port),ipv6) for port,source in required)


def tcp_flow_allowed(chains,source,port,ipv6=False):
    """Follow ordered UFW control flow for a new required TCP connection.

    Unknown matching conditions fail closed; LOG is non-terminal. LOCAL
    addrtype represents this host's storefront destination.
    """
    addr=ipaddress.ip_address(source if source not in ('0.0.0.0','::') else ('2001:db8::10' if ipv6 else '10.77.50.1'))
    dest=ipaddress.ip_address('2001:db8::20' if ipv6 else '10.77.30.10')
    def walk(name,seen):
        if name in seen or len(seen)>20: return 'UNKNOWN'
        for rule in chains.get(name,[]):
            if '-g' in rule or '!' in rule: return 'UNKNOWN'
            t=rule[2:]; values={}; i=0
            while i<len(t):
                if i+1>=len(t): return 'UNKNOWN'
                key,value=t[i:i+2]; values.setdefault(key,[]).append(value); i+=2
            target=values.get('-j',[None])[0]
            if target in ('LOG','NFLOG'): continue
            def val(key): return values.get(key,[None])[0]
            if val('-p') not in (None,'tcp','all'): continue
            # Required test flows have no IPv6 routing extension header.
            if ipv6 and values.get('-m')==['rt'] and val('--rt-type')=='0': continue
            known={'-j','-s','-d','-p','-m','--dport','--sport','--ctstate','-i','-o','--dst-type','--icmp-type','--icmpv6-type'}
            if set(values)-known or any(len(v)!=1 for k,v in values.items() if k!='-m'): return 'UNKNOWN'
            if val('-i')=='lo': continue
            if val('-i') or val('-o') or val('--sport'): return 'UNKNOWN'
            if val('--ctstate') and 'NEW' not in val('--ctstate').split(','): continue
            if val('--dst-type') in ('BROADCAST','MULTICAST'): continue
            if val('--dst-type') not in (None,'LOCAL'): return 'UNKNOWN'
            if val('--dport') and val('--dport')!=str(port): continue
            try:
                if val('-s') and addr not in ipaddress.ip_network(val('-s'),strict=False): continue
                if val('-d') and dest not in ipaddress.ip_network(val('-d'),strict=False): continue
            except ValueError: return 'UNKNOWN'
            if any(m not in ('tcp','conntrack','state','addrtype') for m in values.get('-m',[])): return 'UNKNOWN'
            if target in ('ACCEPT','DROP','REJECT','RETURN'): return target
            if target not in chains: return 'UNKNOWN'
            result=walk(target,seen|{name})
            if result!='RETURN': return result
        return 'RETURN'
    return walk('INPUT',set())=='ACCEPT'

def evaluate(issue,d):
    if issue==17: return d.get('status','').startswith('Status: active\n') and setting(d.get('persistent',''),'ENABLED')=='yes'
    if issue==18:
        return (d.get('active') is True and d.get('persistent_matches') is True and
                firewall_rules_safe(d.get('runtime4','')) and (d.get('ipv6') is False or firewall_rules_safe(d.get('runtime6',''),True)))
    if issue==19: return d.get('profiles',{}).get(PROFILE)=='enforce' and d.get('running') is True and d.get('persistent_enforcing') is True
    if issue==20: return d.get('running') is True and d.get('enabled') is True
    if issue==21: return d.get('running') is True and WATCHES<=watches(d.get('runtime_rules','')) and WATCHES<=watches(d.get('persistent_rules',''))
    if issue==22: return journal_storage(d.get('policy',''))=='persistent' and d.get('logs_present') is True and d.get('running') is True
    if issue==23: return d.get('refresh')==1 and d.get('upgrade')==1 and all(d.get(k) is True for k in ('security_origin','timer','installed','source_usable'))
    if issue==24: return d.get('installed') is True and not {'apache2','apache2-bin','apache2-data','apache2-utils'} & set(d.get('holds',[]))
    return False

def installed(package):
    p=result(['dpkg-query','-W','-f=${db:Status-Status}',package])
    if p.returncode in (0,1): return p.returncode==0 and p.stdout=='installed'
    raise ProbeError('Unknown package query state')

def security_origin(text):
    for line in text.splitlines():
        if re.match(r'\s*Unattended-Upgrade::Allowed-Origins::\s+',line):
            if re.search(r'"(?:\$\{distro_id\}|Ubuntu):(?:\$\{distro_codename\}|noble)-security";',line): return True
        if re.match(r'\s*Unattended-Upgrade::Origins-Pattern::\s+',line):
            if 'origin=Ubuntu' in line and re.search(r'(?:archive|suite)=(?:noble|\$\{distro_codename\})-security',line): return True
    return False


def security_source_usable():
    import datetime
    import time
    # indextargets enumerates targets from the currently enabled source files,
    # not merely old orphaned package lists. No network request each score round.
    targets=run(['apt-get','indextargets','--format','$(IDENTIFIER)|$(RELEASE)|$(FILENAME)'])
    candidates=[]
    for line in targets.splitlines():
        parts=line.split('|')
        if len(parts)==3 and parts[0]=='Packages' and parts[1]=='noble-security':
            p=Path(parts[2])
            if p.is_file(): candidates.append(p)
    if not candidates: return False
    for package in candidates:
        index=package.with_name(package.name.split('_noble-security_',1)[0]+'_noble-security_InRelease')
        if not index.is_file() or time.time()-index.stat().st_mtime>7*86400: continue
        if result(['gpgv','--keyring','/usr/share/keyrings/ubuntu-archive-keyring.gpg',str(index)]).returncode: continue
        text=read(index)
        if not re.search(r'(?m)^Origin: Ubuntu$',text) or not re.search(r'(?m)^Suite: noble-security$',text): continue
        from email.utils import parsedate_to_datetime
        dates=dict(re.findall(r'(?m)^(Date|Valid-Until): (.+)$',text))
        try:
            created=parsedate_to_datetime(dates['Date']).timestamp()
            expires=parsedate_to_datetime(dates['Valid-Until']).timestamp() if 'Valid-Until' in dates else created+7*86400
        except (KeyError,ValueError,TypeError): continue
        if created<=time.time()+300 and time.time()<expires and time.time()-created<7*86400: return True
    return False

def collect(issue):
    if issue==17: return {'status':run(['ufw','status']),'persistent':read('/etc/ufw/ufw.conf')}
    if issue==18:
        status=run(['ufw','status']); ipv6=setting(read('/etc/default/ufw'),'IPV6')=='yes'
        if not status.startswith('Status: active\n'): return {'active':False}
        # user.rules must describe the same ACCEPT rules as the loaded UFW chain.
        live4=run(['iptables-save','-t','filter']); file4=read('/etc/ufw/user.rules')
        aux4=read('/etc/ufw/before.rules')+'\n'+read('/etc/ufw/after.rules')
        matches=persistent_rules_match(live4,file4) and persistent_auxiliary_match(live4,aux4)
        live6=run(['ip6tables-save','-t','filter']) if ipv6 else ''
        if ipv6:
            aux6=read('/etc/ufw/before6.rules')+'\n'+read('/etc/ufw/after6.rules')
            matches=matches and persistent_rules_match(live6,read('/etc/ufw/user6.rules'),True) and persistent_auxiliary_match(live6,aux6,True)
        return {'active':True,'persistent_matches':matches,'runtime4':live4,'runtime6':live6,'ipv6':ipv6}
    if issue==19:
        p=Path('/etc/apparmor.d/usr.sbin.rsyslogd'); text=read(p)
        disabled=Path('/etc/apparmor.d/disable/usr.sbin.rsyslogd').exists()
        complain=Path('/etc/apparmor.d/force-complain/usr.sbin.rsyslogd').exists()
        declaration=next((l for l in text.splitlines() if re.match(r'\s*profile rsyslogd\b',l)),None)
        return {'profiles':json.loads(run(['aa-status','--json'])).get('profiles',{}),
                'running':active('rsyslog'),'persistent_enforcing':bool(declaration) and 'complain' not in declaration and not disabled and not complain}
    if issue==20:
        u=unit('auditd'); return {'running':u.get('ActiveState')=='active','enabled':u.get('UnitFileState')=='enabled'}
    if issue==21:
        if not active('auditd'): return {'running':False}
        return {'running':True,'runtime_rules':run(['auditctl','-l']),
                'persistent_rules':'\n'.join(read(p) for p in Path('/etc/audit/rules.d').glob('*.rules'))}
    if issue==22:
        return {'policy':run(['systemd-analyze','cat-config','systemd/journald.conf']),
                'running':active('systemd-journald'),'logs_present':any(Path('/var/log/journal').glob('*/*.journal'))}
    if issue==23:
        # apt-config reads final merged configuration; no proxy credentials are
        # printed or returned because only selected periodic keys are queried.
        periodic=run(['apt-config','shell','REFRESH','APT::Periodic::Update-Package-Lists','UPGRADE','APT::Periodic::Unattended-Upgrade'])
        values=dict(re.findall(r"(REFRESH|UPGRADE)='([0-9]+)'",periodic))
        # apt-config shell cannot enumerate list children; inspect merged dump
        # internally and return only the approved-origin boolean.
        origin_policy=run(['apt-config','dump'])
        timer=unit('apt-daily-upgrade.timer')
        return {'refresh':int(values.get('REFRESH',0)),'upgrade':int(values.get('UPGRADE',0)),
                'security_origin':security_origin(origin_policy),
                'timer':timer.get('ActiveState')=='active' and timer.get('UnitFileState')=='enabled',
                'installed':installed('unattended-upgrades'),'source_usable':security_source_usable()}
    if issue==24: return {'installed':installed('apache2'),'holds':run(['apt-mark','showhold']).split()}
    return {}

def check(issue): return evaluate(issue,collect(issue))
