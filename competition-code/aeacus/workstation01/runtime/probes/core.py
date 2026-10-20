#!/usr/bin/env python3
"""Read-only effective-state probes. Missing/failed inputs never earn credit."""
import argparse
import json
import pathlib
import re
import subprocess

ISSUES = (5, 6, 16, 29, 30, 32)


def unique_setting(text, key):
    if not isinstance(text, str):
        return None
    values = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        parts = re.split(r'[=\s]+', line, maxsplit=1)
        if len(parts) == 2 and parts[0].lower() == key.lower():
            values.append(parts[1].strip())
    return values[0] if len(values) == 1 else None


def evaluate(issue, data):
    if issue in (5, 6):
        setting = 'permitrootlogin' if issue == 5 else 'permitemptypasswords'
        if 'ssh_contexts' in data:
            contexts=data['ssh_contexts']
            return isinstance(contexts,list) and bool(contexts) and all(unique_setting(text,setting)=='no' for text in contexts)
        return unique_setting(data.get('ssh'), setting) == 'no'
    if issue == 16:
        cmdline = data.get('cmdline')
        return (data.get('selinux') == 'Enforcing'
                and unique_setting(data.get('selinux_config'), 'SELINUX') == 'enforcing'
                and isinstance(cmdline, str)
                and not any(arg in ('selinux=0', 'enforcing=0') for arg in cmdline.split()))
    if issue in (29, 30):
        units = data.get('units', [])
        expected = 2 if issue == 29 else 3
        if len(units) != expected or data.get('process_absent') is not True:
            return False
        for unit in units:
            if unit.get('ActiveState') not in ('inactive', 'failed'):
                return False
            if unit.get('LoadState') == 'not-found':
                continue
            if unit.get('LoadState') != 'loaded' or unit.get('UnitFileState') not in ('disabled', 'masked', 'masked-runtime'):
                return False
            # Runtime-only masking does not survive reboot.
            if unit.get('UnitFileState') == 'masked-runtime':
                return False
        return True
    if issue == 32:
        label = data.get('tmp_label')
        return (data.get('tmp_stat') == '1777 0 0 directory'
                and isinstance(label, str) and ':object_r:tmp_t:' in label)
    return False


def command(argv):
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=15)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def read(path):
    try:
        return pathlib.Path(path).read_text()
    except (OSError, UnicodeError):
        return None


def collect(issue):
    if issue in (5, 6):
        users=('root',) if issue==5 else ('root','jwang','competitor-recovery','alex.admin@corp.summit.test','taylor.admin@corp.summit.test','summit-unknown','summit-employee')
        return {'ssh_contexts':[command(['/usr/sbin/sshd','-T','-C','user=%s,host=workstation01,addr=%s'%(user,addr)]) for user in users for addr in ('10.77.10.50','10.77.20.20')]}
    if issue == 16:
        return {'selinux': command(['/usr/sbin/getenforce']), 'selinux_config': read('/etc/selinux/config'), 'cmdline': read('/proc/cmdline')}
    if issue in (29, 30):
        names = ['avahi-daemon.service', 'avahi-daemon.socket'] if issue == 29 else ['cups.service', 'cups.socket', 'cups.path']
        units = []
        for name in names:
            # systemctl show returns nonzero for missing units; inspect its
            # structured output, then require an explicit not-found state.
            try:
                p = subprocess.run(['systemctl', 'show', name, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'UnitFileState'], text=True, capture_output=True, timeout=15)
                unit = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
                if p.returncode != 0 and unit.get('LoadState') != 'not-found':
                    unit = {}
                units.append(unit)
            except (OSError, subprocess.TimeoutExpired):
                units.append({})
        absent = False
        try:
            p = subprocess.run(['pgrep', '-x', 'avahi-daemon' if issue == 29 else 'cupsd'], capture_output=True, timeout=10)
            absent = p.returncode == 1
        except (OSError, subprocess.TimeoutExpired):
            pass
        return {'units': units, 'process_absent': absent}
    if issue == 32:
        return {'tmp_stat': command(['stat', '-c', '%a %u %g %F', '/tmp']), 'tmp_label': command(['ls', '-Zd', '/tmp'])}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--issue', type=int, choices=ISSUES)
    parser.add_argument('--report', action='store_true')
    args = parser.parse_args()
    if args.report:
        print(json.dumps({str(i): {'pass': evaluate(i, data), 'observed': data} for i in ISSUES for data in [collect(i)]}, indent=2))
    elif args.issue is not None:
        print('PASS' if evaluate(args.issue, collect(args.issue)) else 'FAIL')
    else:
        parser.error('Specify --issue or --report')


if __name__ == '__main__':
    main()
