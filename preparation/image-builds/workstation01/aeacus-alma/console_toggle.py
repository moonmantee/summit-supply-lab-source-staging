#!/usr/bin/env python3
"""Organizer console helper for the reviewed WORKSTATION01 AlmaLinux image.

Run with sudo: python3 console_toggle.py solve|reset|status
Recovery is private and retained. No SSH, plaintext scorer config, or score override.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time

BASE = Path('/var/backups/summit-console-toggle-v1')
RUNTIME = Path('/opt/aeacus/finish_runtime.py')
REPORT = Path('/opt/aeacus/assets/ScoringReport.html')
INTERFACE = 'enp6s18'
REVIEWED_RUNTIME = '67d3949fbdcb7dd5a045a0914e17a37a4d1e98e9688214e79c2624296ecb0c8e'


def adapt_interface(source, interface):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', interface):
        raise ValueError('Invalid network interface')
    return source.replace('ens160', interface)


def report_matches(path, expected, started):
    try:
        text = path.read_text()
        return (path.stat().st_mtime >= started and text.rstrip().endswith('</html>')
                and re.search(r'(?<!\d)' + str(expected)
                              + r' out of 100 points received\b', text) is not None)
    except (OSError, UnicodeError):
        return False


def fill_answers(root, answers):
    prepared = []
    for number, answer in answers.values():
        path = root / ('Forensic-Question-%d.txt' % number)
        text, count = re.subn(r'^Answer[ \t]*=.*$',
                             lambda match: 'Answer = ' + answer,
                             path.read_text(), flags=re.M)
        if count != 1:
            raise RuntimeError('Unexpected answer template: ' + str(path))
        prepared.append((path, text))
    for path, text in prepared:
        path.write_text(text)


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True,
                          timeout=240, env=dict(os.environ, LC_ALL='C')).stdout.strip()


def private_directory(path):
    if path.is_symlink():
        raise RuntimeError('Symlink recovery directory refused')
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise RuntimeError('Recovery directory must be root-owned and private')


def save_state(state):
    temporary = BASE / 'state.tmp'
    if temporary.is_symlink():
        raise RuntimeError('Unsafe temporary state path')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(BASE / 'state.json')


def load_runtime():
    source = RUNTIME.read_text()
    if hashlib.sha256(source.replace('\r\n', '\n').encode()).hexdigest() != REVIEWED_RUNTIME:
        raise RuntimeError('Installed repair code differs from reviewed version; no repairs made')
    previous = sys.argv
    sys.argv = [str(RUNTIME), '--verify-only']
    namespace = {'__name__': 'summit_console_runtime', '__file__': str(RUNTIME)}
    try:
        exec(compile(adapt_interface(source, INTERFACE), str(RUNTIME), 'exec'), namespace)
    finally:
        sys.argv = previous
    namespace['BACKUP'] = BASE / 'session'
    namespace['RES'] = BASE / 'resources'
    return namespace


def check_state(m, repaired):
    states = m['checks']()
    wrong = [i for i, passed in states.items() if passed != repaired]
    if wrong:
        raise RuntimeError('Native checks disagree: ' + ', '.join(map(str, sorted(wrong))))


def refresh_report(expected):
    run('systemctl', 'stop', 'summit-aeacus.service')
    REPORT.unlink(missing_ok=True)
    started = time.time()
    run('systemctl', 'start', 'summit-aeacus.service')
    for _ in range(180):
        if report_matches(REPORT, expected, started):
            print('LIVE AEACUS: %d/100 verified.' % expected, flush=True)
            return
        if run('systemctl', 'is-active', 'summit-aeacus.service') != 'active':
            raise RuntimeError('Scoring service stopped')
        time.sleep(1)
    raise RuntimeError('Fresh live report did not reach %d/100; inspect the report' % expected)


def restore(m, packages, state):
    snapshot = m['Snapshot'].from_record(BASE / 'session/baseline',
                                        m['target_paths'](), packages)
    snapshot.restore()
    # The fresh snapshot has normal /tmp permissions (2 points). Restore ONLY
    # the intentionally planted mode from the original competition record.
    os.chmod('/tmp', state['planted_tmp_mode'])
    run('restorecon', '/tmp')
    check_state(m, False)
    refresh_report(0)
    state['phase'] = 'reset'
    save_state(state)


def solve(m):
    if (BASE / 'state.json').exists():
        raise RuntimeError('A session already exists. Use reset or status; recovery is retained')
    if not Path('/sys/class/net/' + INTERFACE).exists():
        raise RuntimeError('Expected Proxmox interface enp6s18 is absent')
    current = m['checks']()
    if {i for i, passed in current.items() if passed} - {32}:
        raise RuntimeError('Image changed since preflight; expected only check 32 or no credit')
    m['health'](scoring=True)
    if not re.search(r'^enabled\s+1$', run('auditctl', '-s'), re.M):
        raise RuntimeError('Audit rules are immutable/disabled; refusing repair')
    packages = m['Packages']()  # Verify pinned, signed offline recovery RPMs first.
    original = json.loads(Path('/opt/aeacus/helpers/finish-backup.json').read_text())
    original_root = Path(original['path'])
    if not re.fullmatch(r'/var/backups/summit-workstation01-finish(?:-retry\d+)?', str(original_root)):
        raise RuntimeError('Unexpected original recovery location')
    original_index = json.loads((original_root / 'competition-start/index.json').read_text())
    mode = original_index['tmp_mode']
    if mode != 0o777:
        raise RuntimeError('Original planted /tmp mode differs; no changes made')
    private_directory(BASE / 'session')
    private_directory(BASE / 'resources')
    # Existing marker recovery verifies the original, inert payload against this hash.
    (BASE / 'resources/artifact-hashes.json').write_text(
        json.dumps({'systemd-marker.sh': m['scenario'].HASH}))
    probe = Path('/opt/aeacus/probes/access.py')
    before = probe.read_text()
    after = adapt_interface(before, INTERFACE)
    if '--get-zone-of-interface=' + INTERFACE not in after:
        raise RuntimeError('Unexpected firewall probe; no probe changes made')
    compile(after, str(probe), 'exec')
    (BASE / 'original-access.py').write_text(before)
    # A Proxmox device-name correction, without changing scoring criteria.
    probe.write_text(after)
    run('restorecon', str(probe))
    exec(compile(after, str(probe), 'exec'), m['access'].__dict__)
    m['Snapshot'](BASE / 'session/baseline', m['target_paths'](), packages)
    state = {'phase': 'ready', 'interface': INTERFACE, 'planted_tmp_mode': mode}
    save_state(state)
    print('Recovery captured at ' + str(BASE) + '; starting real repairs.', flush=True)
    public_paths = dict(m['scenario'].FORENSICS_FILES)
    try:
        run('systemctl', 'stop', 'summit-aeacus.service')
        # Remove the obsolete VMware binding only; leave Proxmox IP/DNS unchanged.
        for permanent in (False, True):
            prefix = ['firewall-cmd'] + (['--permanent'] if permanent else [])
            for zone in run(*(prefix + ['--get-zones'])).split():
                query = prefix + ['--zone=' + zone]
                if 'ens160' in run(*(query + ['--list-interfaces'])).split():
                    run(*(query + ['--remove-interface=ens160']))
        due = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
        m['write'](m['TIMER_DROP'], '[Timer]\nOnBootSec=\nOnUnitActiveSec=\n'
                   'OnCalendar=\nOnCalendar=' + due.strftime('%Y-%m-%d %H:%M:%S UTC')
                   + '\nPersistent=false\nRandomizedDelaySec=0\n')
        uuid = json.loads((BASE / 'session/baseline/index.json').read_text())['nm_uuid']
        try:
            m['full_repair'](uuid)
        finally:
            m['scenario'].FORENSICS_FILES = public_paths
        fill_answers(Path('/srv/summit-competition'), m['scenario'].ANSWERS)
        check_state(m, True)
        refresh_report(100)
        state['phase'] = 'solved'
        save_state(state)
        print('Left at 100/100. Run the same helper with reset to return to 0/100.')
    except BaseException:
        print('Repair did not finish; restoring the starting weaknesses.', flush=True)
        try:
            restore(m, packages, state)
        except BaseException as recovery:
            state['phase'] = 'recovery-needed'
            save_state(state)
            print('RECOVERY NEEDS ATTENTION: ' + str(recovery), file=sys.stderr)
            print('Keep recovery data; run this helper with reset.', file=sys.stderr)
        raise


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('solve', 'reset', 'status'):
        raise SystemExit('Usage: sudo python3 /root/ws-score.py solve|reset|status')
    action = sys.argv[1]
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'workstation01':
        raise SystemExit('Run with sudo on WORKSTATION01 only')
    if 'VERSION_ID="9.8"' not in Path('/etc/os-release').read_text():
        raise SystemExit('Expected AlmaLinux 9.8')
    os.umask(0o077)
    os.environ.pop('SUMMIT_FORENSICS_ROOT', None)
    import fcntl
    private_directory(BASE)
    with (BASE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        m = load_runtime()
        if action == 'status':
            print('Currently credited checks:', [i for i, passed in m['checks']().items() if passed])
            print('Report:', REPORT)
        elif action == 'solve':
            solve(m)
        else:
            state = json.loads((BASE / 'state.json').read_text())
            if state.get('interface') != INTERFACE or state.get('planted_tmp_mode') != 0o777:
                raise RuntimeError('Unexpected recovery state')
            restore(m, m['Packages'](), state)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('Interrupted. Recovery is retained; use reset if a session was captured.')
    except Exception as error:
        raise SystemExit('STOP: ' + str(error))
