"""Three synthetic incident questions; answers are plain data, never commands."""
import hashlib
import os
from pathlib import Path
import re
import stat

ISSUES=(38,39,40)
ROOT=Path('/srv/summit-shop01-forensics')
HASHES={
 38:'3696668f6f827407e5ff469091d3da2449de15b914b45b1afe87aeb5436f3ecb',
 39:'43c74eee8d529ff9bdae4750a13ab566fc1a10a63569b02db56e00b1c29768ef',
 40:'cb3d9126b0ba020043c3c9301b97bf0835f1c6c430757c55a04aa3e73e180adb',
}


def question_path(issue):
    if issue not in ISSUES: raise ValueError('Unsupported forensic objective')
    return ROOT/('Forensic-Question-%d.txt'%(issue-37))


def evaluate(issue,text):
    values=re.findall(r'^Answer[ \t]*=[ \t]*([^\r\n]*)$',text,re.M)
    return (issue in HASHES and len(values)==1 and
            hashlib.sha256(values[0].strip().encode()).hexdigest()==HASHES[issue])


def check_file(issue,path):
    path=Path(path)
    if any(p.is_symlink() for p in [path,*path.parents]): return False
    try:
        if not stat.S_ISREG(path.lstat().st_mode): return False
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_NOFOLLOW',0))
    except FileNotFoundError: return False
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>16384: return False
        content=os.read(fd,16385)
        if len(content)>16384: return False
        try: text=content.decode('utf-8')
        except UnicodeDecodeError: return False
        return evaluate(issue,text)
    finally: os.close(fd)


def check(issue): return check_file(issue,question_path(issue))
