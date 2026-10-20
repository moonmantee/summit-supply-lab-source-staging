import re
from acceptance_helpers import require_state


def require_rehearsal(data):
    require_state(data.get('repaired',{}),True)
    require_state(data.get('restored',{}),False)

def require_report(html):
    score=re.search(r'(\d+) out of (\d+) points received',html)
    issues=re.search(r'(\d+) out of (\d+) scored security issues fixed',html)
    if not score or tuple(map(int,score.groups()))!=(0,100) or not issues or tuple(map(int,issues.groups()))!=(0,40):
        raise ValueError('Expected encrypted live report: 0/100, zero of forty objectives repaired')


def wait_scoring_report(report,alive,timeout=60):
    """Require a complete report after the caller removes the previous report."""
    from pathlib import Path
    import time
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if not alive(): raise RuntimeError('Encrypted scoring runtime exited before verification')
        try: html=Path(report).read_text()
        except FileNotFoundError: html=''
        if html.rstrip().endswith('</html>'):
            require_report(html)
            return
        time.sleep(0.25)
    raise RuntimeError('Timed out waiting for a fresh encrypted scoring report')


def private_phocus(directory,binary,runtime=None):
    """Use workstation01's proven private mount namespace for fixed-path Phocus."""
    from pathlib import Path
    import os,shutil,signal,subprocess
    directory=Path(directory).resolve()
    shutil.copy2(binary,directory/'phocus')
    (directory/'phocus').chmod(0o700)
    report=directory/'assets/ScoringReport.html'
    report.unlink(missing_ok=True)
    child_code="import os,subprocess,sys; subprocess.run(['/usr/bin/mount','--bind',sys.argv[1],'/opt/aeacus'],check=True); os.chdir('/opt/aeacus'); os.execv('/opt/aeacus/phocus',['/opt/aeacus/phocus'])"
    extra=[]
    if runtime is not None:
        runtime=Path(runtime).resolve()
        if not runtime.is_dir(): raise RuntimeError('Missing candidate probe runtime')
        child_code=child_code.replace("os.chdir('/opt/aeacus');", "subprocess.run(['/usr/bin/mount','--bind',sys.argv[2],'/opt/summit-shop01'],check=True); os.chdir('/opt/aeacus');")
        extra=[str(runtime)]
    with (directory/'encrypted-phocus.log').open('wb') as log:
        process=subprocess.Popen(['/usr/bin/unshare','--mount','--propagation','private','/usr/bin/python3','-c',child_code,str(directory)]+extra,
                                 cwd=directory,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            wait_scoring_report(report,lambda:process.poll() is None)
        except Exception as error:
            log.flush()
            detail=(directory/'encrypted-phocus.log').read_text(errors='replace')[-2000:]
            raise RuntimeError('Private encrypted-engine verification failed: '+str(error)+'\n'+detail) from error
        finally:
            try: os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=5)


def cutover_transaction(prepare,stop,snapshot,apply,rollback,resume,cleanup):
    stopped=False; captured=False
    try:
        candidate=prepare()
        stopped=True
        stop()
        snapshot()
        captured=True
        apply(candidate)
    except BaseException:
        try:
            if captured: rollback()
            elif stopped: resume()
        finally: cleanup()
        raise


def require_user_viewer(run,uid):
    run(['runuser','-u','jwang','--','env','XDG_RUNTIME_DIR=/run/user/'+str(uid),
         'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(uid)+'/bus',
         'systemctl','--user','is-active','--quiet','summit-report-viewer'])
