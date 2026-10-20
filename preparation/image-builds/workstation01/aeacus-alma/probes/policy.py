#!/usr/bin/env python3
"""Read-only application, update, and file-policy probes."""
import argparse
import configparser
import fnmatch
import json
import os
import pathlib
import re
import stat
import subprocess

ISSUES=(9,10,12,13,14,23,33,35)


def browser_protected(policy, keys):
    if not isinstance(policy,dict):
        return False
    policies=policy.get('policies',{})
    if not isinstance(policies,dict):
        return False
    prefs=policies.get('Preferences',{})
    if not isinstance(prefs,dict):
        return False
    return all(isinstance(prefs.get(k),dict) and prefs[k].get('Value') is True and prefs[k].get('Status')=='locked' for k in keys)


def update_allowed(package, files):
    if '/etc/dnf/dnf.conf' not in files:
        return False
    try:
        for path,text in files.items():
            cfg=configparser.ConfigParser(interpolation=None,strict=True)
            cfg.read_string(text)
            for section in cfg.sections():
                settings=cfg[section]
                if section!='main' and settings.get('enabled','1').strip()=='0':
                    continue
                excluded=re.split(r'[,\s]+',settings.get('exclude','')+' '+settings.get('excludepkgs',''))
                # Match both package names and RPM-style version suffixes.
                if any(p and (fnmatch.fnmatchcase(package,p) or fnmatch.fnmatchcase(package+'-999',p)) for p in excluded):
                    return False
                included=[p for p in re.split(r'[,\s]+',settings.get('includepkgs','')) if p]
                if included and not any(fnmatch.fnmatchcase(package,p) or fnmatch.fnmatchcase(package+'-999',p) for p in included):
                    return False
        return True
    except (configparser.Error,TypeError,AttributeError):
        return False


def path_protected(paths, acl_ok):
    return bool(paths) and acl_ok is True and paths[-1].get('kind')=='file' and all(p.get('uid')==0 and isinstance(p.get('mode'),int) and not p['mode'] & 0o022 and p.get('kind') in ('file','directory') for p in paths)


def cockpit_absent(code, output):
    return code==1 and isinstance(output,str) and output.strip()=='package cockpit-ws is not installed'


def run(argv):
    try:
        return subprocess.run(argv,text=True,capture_output=True,timeout=20,env=dict(os.environ,LC_ALL='C'))
    except (OSError,subprocess.TimeoutExpired):
        return None


def secure_file(filename):
    p=pathlib.Path(filename)
    paths=[]
    try:
        for node in list(reversed(p.parents))+[p]:
            s=node.lstat()
            kind='directory' if stat.S_ISDIR(s.st_mode) else 'file' if stat.S_ISREG(s.st_mode) else 'other'
            paths.append(dict(uid=s.st_uid,mode=stat.S_IMODE(s.st_mode),kind=kind))
            acl=run(['getfacl','-cp',str(node)])
            if acl is None or acl.returncode!=0:
                return False
            lines=[l.split('#',1)[0].strip() for l in acl.stdout.splitlines() if l.strip()]
            mask=next((l.split(':')[-1] for l in lines if l.startswith('mask::')),'rwx')
            for line in lines:
                entries=line.removeprefix('default:').split(':')
                if len(entries)==3 and entries[0] in ('user','group') and entries[1] and entries[1] not in ('root','0') and 'w' in entries[2] and 'w' in mask:
                    return False
        return path_protected(paths,True)
    except (OSError,ValueError):
        return False


def check(issue):
    if issue in (9,10):
        keys=['browser.safebrowsing.phishing.enabled','browser.safebrowsing.malware.enabled'] if issue==9 else ['browser.safebrowsing.downloads.enabled']
        try:
            policy=json.loads(pathlib.Path('/etc/firefox/policies/policies.json').read_text())
            return browser_protected(policy,keys)
        except (OSError,ValueError,TypeError,AttributeError):
            return False
    if issue in (12,33):
        return secure_file('/etc/summit-workstation/app.conf' if issue==12 else '/etc/profile.d/summit-workstation.sh')
    if issue in (13,14):
        try:
            files={str(p):p.read_text() for p in [pathlib.Path('/etc/dnf/dnf.conf')]+list(pathlib.Path('/etc/yum.repos.d').glob('*.repo'))}
            return update_allowed('firefox' if issue==13 else 'gedit',files)
        except (OSError,UnicodeError):
            return False
    if issue==23:
        p=run(['systemd-analyze','cat-config','systemd/journald.conf'])
        if p is None or p.returncode!=0:
            return False
        values=re.findall(r'^\s*Storage\s*=\s*(\w+)\s*$',p.stdout,re.M)
        storage=values[-1] if values else 'auto'
        return storage in ('auto','persistent') and pathlib.Path('/var/log/journal').is_dir()
    if issue==35:
        p=run(['rpm','-q','cockpit-ws'])
        if p is None or not cockpit_absent(p.returncode,p.stdout):
            return False
        p=run(['systemctl','show','cockpit.socket','-p','ActiveState','-p','UnitFileState','-p','LoadState'])
        if p is None:
            return False
        settings=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
        return settings.get('ActiveState')=='inactive' and (settings.get('LoadState')=='not-found' or settings.get('UnitFileState') in ('disabled','masked'))
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
