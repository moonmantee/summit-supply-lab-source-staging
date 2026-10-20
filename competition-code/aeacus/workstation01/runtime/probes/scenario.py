#!/usr/bin/env python3
"""Read-only scenario checks; synthetic markers never refer to real secrets."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from policy import run

ISSUES=(17,18,19,24,25,27,28,34,36,37,38)
PAYLOAD=b'#!/bin/sh\n# SUMMIT-TRAINING-SYSTEMD-MARKER\nprintf "training marker\\n" >> /var/tmp/summit-training-systemd.log\n'
HASH=hashlib.sha256(PAYLOAD).hexdigest()
FORENSICS_FILE='/srv/summit-competition/Forensics.txt'
FORENSICS_FILES={issue:str(Path(os.environ.get('SUMMIT_FORENSICS_ROOT','/srv/summit-competition'))/('Forensic-Question-%d.txt'%number)) for issue,number in ((17,1),(18,2),(19,3))}
CONTENT_USERS=('jwang','alex.admin@corp.summit.test','taylor.admin@corp.summit.test','competitor-recovery')
ANSWERS={17:(1,'summit-contractor'),18:(2,'summit-marker.timer; summit-marker.service; /usr/local/lib/summit-training/systemd-marker.sh'),19:(3,HASH)}


def scan_clean(roots,markers,max_bytes=268435456,max_files=20000):
    """Scan complete declared scope; renamed files count, errors fail closed.

    Never follow a symlink or read a device. A symlink in the declared scope
    conservatively fails rather than permitting content to escape the scan.
    """
    total=0
    files=0
    if not markers or not roots:
        return False
    try:
        for root in roots:
            base=Path(root)
            if not base.is_dir() or base.is_symlink():
                return False
            for directory,dirs,names in os.walk(base,followlinks=False,onerror=lambda e: (_ for _ in ()).throw(e)):
                for name in dirs+names:
                    p=Path(directory)/name
                    s=p.lstat()
                    if stat.S_ISLNK(s.st_mode):
                        return False
                    if stat.S_ISDIR(s.st_mode):
                        continue
                    if not stat.S_ISREG(s.st_mode):
                        return False
                    files+=1
                    total+=s.st_size
                    if files>max_files or total>max_bytes:
                        return False
                    with p.open('rb') as f:
                        carry=b''
                        while True:
                            block=f.read(65536)
                            if not block:
                                break
                            data=carry+block
                            if any(m in data for m in markers):
                                return False
                            carry=data[-max(map(len,markers)):]
        return True
    except (OSError,ValueError):
        return False


def answers_correct(text,number,expected):
    if not isinstance(text,str):
        return False
    values=re.findall(r'^\s*Q%d\s*=\s*(.*?)\s*$'%number,text,re.M)
    return values==[expected]


def question_answer_correct(text,expected):
    if not isinstance(text,str):
        return False
    values=re.findall(r'^Answer[ \t]*=[ \t]*(.*?)[ \t]*$',text,re.M)
    return values==[expected]


def account_disabled(data,retain):
    if data.get('exists') is False:
        return not retain
    return data.get('exists') is True and data.get('locked') is True and data.get('expired') is True and data.get('shell') in ('/sbin/nologin','/usr/sbin/nologin','/bin/false','/usr/bin/false') and data.get('keys_absent') is True


def account_state(name):
    # Use files backend: scenario identities must remain local, never CORP.
    p=run(['getent','-s','files','passwd',name])
    if p is None:
        return {}
    if p.returncode==2 and not p.stdout:
        return {'exists':False}
    try:
        if p.returncode!=0:
            return {}
        fields=p.stdout.strip().split(':')
        if len(fields)!=7 or fields[0]!=name:
            return {}
        s=run(['getent','-s','files','shadow',name])
        if s is None or s.returncode!=0:
            return {}
        shadow=s.stdout.strip().split(':')
        if len(shadow)!=9 or shadow[0]!=name:
            return {}
        today=(datetime.date.today()-datetime.date(1970,1,1)).days
        expiry=int(shadow[7]) if shadow[7] else -1
        home=Path(fields[5])
        keys=home/'.ssh'
        key_absent=not keys.exists() or (not keys.is_symlink() and not any(keys.iterdir()))
        # Never return password hashes in reports.
        return dict(exists=True,locked=shadow[1].startswith(('!','*')),expired=0<=expiry<today,shell=fields[6],keys_absent=key_absent)
    except (OSError,ValueError):
        return {}


def text_read(path):
    try:
        return Path(path).read_text()
    except (OSError,UnicodeError):
        return None


def absent_package(name):
    p=run(['rpm','-q',name])
    return p is not None and p.returncode==1 and p.stdout.strip()=='package %s is not installed'%name


def check(issue):
    if issue in ANSWERS:
        n,value=ANSWERS[issue]
        evidence=Path('/opt/summit-evidence/systemd-marker.sh')
        try:
            if evidence.read_bytes()!=PAYLOAD:
                return False
        except OSError:
            return False
        return question_answer_correct(text_read(FORENSICS_FILES[issue]),value)
    if issue in (24,25):
        marker=b'SUMMIT-TRAINING-CRON-MARKER' if issue==24 else b'SUMMIT-TRAINING-SYSTEMD-MARKER'
        # These scopes contain system symlinks. Inspect file contents explicitly,
        # resolving symlinks; missing/broken links or permissions fail closed.
        roots=['/etc/cron.d','/var/spool/cron','/usr/local/lib/summit-training','/usr/local/bin'] if issue==24 else ['/etc/systemd/system','/usr/local/lib/summit-training','/usr/local/bin']
        for root in roots:
            p=Path(root)
            if not p.is_dir():
                return False
            try:
                for f in p.rglob('*'):
                    if f.is_dir():
                        continue
                    if not f.is_file() or marker in f.read_bytes():
                        return False
            except OSError:
                return False
        if issue==25:
            # Check each live unit separately, not just removal of unit files.
            for unit in ('summit-marker.timer','summit-marker.service'):
                p=run(['systemctl','show',unit,'-p','ActiveState','-p','LoadState','-p','UnitFileState'])
                if p is None:
                    return False
                state=dict(l.split('=',1) for l in p.stdout.splitlines() if '=' in l)
                if state.get('ActiveState')!='inactive' or not (state.get('LoadState')=='not-found' or state.get('UnitFileState') in ('disabled','masked')):
                    return False
        return True
    if issue in (27,28,34):
        marker={27:b'SUMMIT-TRAINING-CREDENTIALS',28:b'SUMMIT-TRAINING-PERSONAL-MEDIA',34:b'SUMMIT-TRAINING-OFFLINE-GAME'}[issue]
        roots=['/home/'+user+'/'+folder for user in CONTENT_USERS for folder in ('Desktop','Documents','Downloads')]
        roots+=['/srv/summit-competition/Downloads']
        if issue==34:
            roots+=['/usr/local/share/summit-games']
        return scan_clean(roots,[marker])
    if issue==36:
        return absent_package('nmap') and all(not Path(p).exists() for p in ('/usr/bin/nmap','/usr/local/bin/nmap'))
    if issue in (37,38):
        return account_disabled(account_state('summit-unknown' if issue==37 else 'summit-departed'),issue==38)
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
