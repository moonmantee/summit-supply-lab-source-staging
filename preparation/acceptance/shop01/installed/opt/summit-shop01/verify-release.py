#!/usr/bin/env python3
"""Root-only post-deployment and post-reboot acceptance; emits no secrets."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from acceptance_helpers import require_state
from release_helpers import require_report, require_user_viewer
from validate_results import collect


def main():
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='shop01':
        raise RuntimeError('Run with sudo on shop01')
    root=Path(__file__).resolve().parent
    require_state(collect(root),False)
    for path in [root,root/'probes',*list((root/'probes').glob('*.py')),
                 Path('/var/lib/summit-shop01'),Path('/var/lib/summit-shop01/private.json'),
                 Path('/opt/aeacus/scoring.dat')]:
        st=path.lstat()
        if path.is_symlink() or st.st_uid!=0 or st.st_mode & 0o077:
            raise RuntimeError('Private scoring ownership/mode failed: '+str(path))
    if Path('/opt/aeacus/scoring.conf').exists(): raise RuntimeError('Production plaintext scoring config remains')
    if Path('/home/jwang/shop01-setup').exists(): raise RuntimeError('Participant-accessible organizer staging remains')
    for unit in ('summit-aeacus','ssh','sssd','apache2','rsyslog'):
        subprocess.run(['systemctl','is-active','--quiet',unit],check=True)
    import pwd
    require_user_viewer(lambda args:subprocess.run(args,check=True),pwd.getpwnam('jwang').pw_uid)
    if subprocess.check_output(['systemctl','show','summit-aeacus','-p','User','--value'],text=True).strip()!='root':
        raise RuntimeError('Scorer must run as root')
    if subprocess.check_output(['systemctl','is-enabled','summit-aeacus'],text=True).strip()!='enabled':
        raise RuntimeError('Scorer not enabled at boot')
    report=Path('/opt/aeacus/assets/ScoringReport.html')
    old=report.stat().st_mtime_ns
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        if report.stat().st_mtime_ns!=old:
            require_report(report.read_text())
            break
        time.sleep(1)
    else: raise RuntimeError('Scoring report did not refresh')
    if report.stat().st_mode & 0o444!=0o444: raise RuntimeError('Participant report unreadable')
    import urllib.request
    import urllib.error
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8765/ScoringReport.html',timeout=5) as response:
        require_report(response.read(262144).decode())
    with opener.open('http://127.0.0.1:8765/ReadMe.html',timeout=5) as response:
        if 'summit_editor' not in response.read(262144).decode(): raise RuntimeError('Updated participant ReadMe missing')
    for name in ('scoring.dat','scoring.conf','../scoring.dat'):
        try: opener.open('http://127.0.0.1:8765/'+name,timeout=5)
        except urllib.error.HTTPError as e:
            if e.code!=404: raise RuntimeError('Unexpected scoring-file HTTP response')
        else: raise RuntimeError('Private scoring configuration exposed by viewer')
    sys.path.insert(0,str(root/'probes'))
    import web
    status,body=web.fetch('/')
    if status!=200 or not web.healthy_catalog(body) or web.fetch('/order-history.php')[0]!=200:
        raise RuntimeError('Storefront/order history failed')
    for user in ('jwang','summit_editor'):
        sudo=subprocess.check_output(['sudo','-ll','-U',user],text=True)
        if 'RunAsUsers: ALL' not in sudo or '\tALL' not in sudo:
            raise RuntimeError('Administrator recovery sudo failed')
    print('Encrypted live scorer: 0/100; all forty FAIL, no ERROR states; report refresh PASS.')
    print('PHP storefront/order history, required services and recovery sudo PASS.')
    print('Fresh authorized domain login and independent service scoring still require release confirmation.')


if __name__=='__main__': main()
