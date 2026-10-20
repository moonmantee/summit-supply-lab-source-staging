#!/usr/bin/env bash
# Inventory and private recovery archive only: does not stage weaknesses.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'Run with sudo at the shop01 console.'; exit 1; }
[[ $(hostname -s) == shop01 ]] || { echo 'Wrong host.'; exit 1; }
[[ $(. /etc/os-release; printf '%s' "$ID") == ubuntu ]] || exit 1
[[ ! -e /home/jwang/shop01-baseline.json && ! -L /home/jwang/shop01-baseline.json ]] || { echo 'Existing baseline: preserve it before repeating.'; exit 1; }
backup_dir=$(mktemp -d /var/backups/summit-shop01-baseline-XXXXXXXX)
chmod 700 "$backup_dir"
targets=()
for path in /etc/passwd /etc/group /etc/shadow /etc/gshadow /etc/ssh/sshd_config /etc/ssh/sshd_config.d /etc/pam.d /etc/security /var/lib/pam /etc/sudoers /etc/sudoers.d /etc/ufw /etc/default/ufw /etc/apparmor.d /etc/audit /etc/systemd/journald.conf /etc/systemd/journald.conf.d /etc/apt/apt.conf.d /etc/apache2 /etc/summit /etc/ssl/private/summit-shop01.key /etc/ssl/certs/summit-shop01.crt /var/www/summit /home/jwang/.ssh /opt/aeacus /etc/systemd/system/summit-aeacus.service /etc/cron.d; do
  [[ ! -e "$path" && ! -L "$path" ]] || targets+=("${path#/}")
done
tar --acls --xattrs --numeric-owner -C / -czf "$backup_dir/original-state.tar.gz" "${targets[@]}"
chmod 600 "$backup_dir/original-state.tar.gz"
sha256sum "$backup_dir/original-state.tar.gz" > "$backup_dir/archive.sha256"
export SUMMIT_SHOP_BACKUP="$backup_dir"
python3 - <<'PY'
import datetime, hashlib, json, os, pathlib, pwd, subprocess

def run(argv, timeout=15):
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                           env={**os.environ, 'LC_ALL': 'C'})
        return {'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'exit': None, 'error': type(e).__name__}

commands = {
 'identity': ['id', 'jwang'],
 'local_users': ['getent', '-s', 'files', 'passwd'],
 'local_groups': ['getent', '-s', 'files', 'group'],
 'domain': ['realm', 'list'],
 'sshd_root': ['/usr/sbin/sshd', '-T', '-C', 'user=root,host=shop01,addr=10.77.10.50'],
 'sshd_jwang': ['/usr/sbin/sshd', '-T', '-C', 'user=jwang,host=shop01,addr=10.77.10.50'],
 'sudo_jwang': ['sudo', '-ll', '-U', 'jwang'],
 'sudo_syntax': ['visudo', '-c'],
 'firewall': ['ufw', 'status', 'numbered'],
 'firewall_added': ['ufw', 'show', 'added'],
 'apparmor': ['aa-status', '--json'],
 'audit_status': ['auditctl', '-s'],
 'audit_rules': ['auditctl', '-l'],
 'apache_syntax': ['apache2ctl', '-t'],
 'apache_vhosts': ['apache2ctl', '-t', '-D', 'DUMP_VHOSTS'],
 'apache_includes': ['apache2ctl', '-t', '-D', 'DUMP_INCLUDES'],
 'apache_modules': ['apache2ctl', '-M'],
 'packages': ['dpkg-query', '-W', 'apache2', 'php', 'php-mysql', 'ufw', 'apparmor', 'apparmor-utils', 'auditd', 'acl', 'libpam-pwquality', 'libpam-modules', 'unattended-upgrades', 'sssd-ad', 'realmd'],
 'package_holds': ['apt-mark', 'showhold'],
 'timers': ['systemctl', 'list-timers', '--all', '--no-pager'],
 'journal_policy': ['systemd-analyze', 'cat-config', 'systemd/journald.conf'],
 'apt_periodic': ['apt-config', 'shell', 'REFRESH', 'APT::Periodic::Update-Package-Lists', 'UPGRADE', 'APT::Periodic::Unattended-Upgrade'],
 'permissions': ['stat', '-c', '%U:%G %a %n', '/etc/shadow', '/etc/sudoers', '/etc/apache2', '/var/www/summit', '/etc/ssl/private/summit-shop01.key', '/etc/summit/database.php'],
 'acls': ['getfacl', '-p', '/etc/shadow', '/etc/sudoers', '/etc/apache2', '/var/www/summit', '/etc/ssl/private/summit-shop01.key'],
 'routing': ['ip', 'route'],
 'ipv6_addresses': ['ip', '-6', 'addr'],
 'disk': ['df', '-h', '/'],
}
data = {'collected_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'backup_directory': os.environ['SUMMIT_SHOP_BACKUP'],
        'snapshot_verified': False, 'changes_staged': False,
        'checks': {name: run(argv) for name, argv in commands.items()}}
data['services'] = {s: run(['systemctl', 'show', s, '-p', 'LoadState', '-p', 'ActiveState', '-p', 'UnitFileState'])
                    for s in ['apache2', 'ssh', 'summit-aeacus', 'sssd', 'ufw', 'apparmor', 'auditd', 'cron', 'systemd-journald']}
allowed = ['/etc/pam.d/common-auth', '/etc/pam.d/common-account', '/etc/pam.d/common-password',
           '/etc/security/pwquality.conf', '/etc/security/pwhistory.conf', '/etc/security/faillock.conf',
           '/etc/ufw/ufw.conf', '/etc/default/ufw', '/etc/apache2/sites-available/summit-shop.conf']
data['policy_files'] = {f: pathlib.Path(f).read_text(errors='replace') for f in allowed if pathlib.Path(f).is_file()}
# Collect application metadata only. Never export PHP source, database credentials,
# shadow values, authorized key contents or TLS private key material.
data['application_files'] = []
for p in pathlib.Path('/var/www/summit').rglob('*'):
    if p.is_file() and not p.is_symlink():
        st = p.stat()
        data['application_files'].append({'path': str(p), 'uid': st.st_uid, 'gid': st.st_gid,
                                         'mode': oct(st.st_mode & 0o7777), 'bytes': st.st_size,
                                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
data['web'] = {name: run(['curl', '--max-time', '8', '--silent', '--show-error',
                         '--cacert', '/etc/ssl/certs/summit-shop01.crt',
                         '--resolve', 'shop01.corp.summit.test:443:127.0.0.1',
                         '-o', '/dev/null', '-w', '%{http_code}',
                         'https://shop01.corp.summit.test' + path], 12)
               for name, path in [('home', '/'), ('order_history', '/order-history.php'), ('static_backup', '/index.html.backup')]}
out = pathlib.Path('/home/jwang/shop01-baseline.json')
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump(data, f, indent=2)
account = pwd.getpwnam('jwang')
os.chown(out, account.pw_uid, account.pw_gid)
print('Non-secret inventory:', out)
print('Private recovery archive:', data['backup_directory'])
print('Collection complete; no weaknesses or production scorer changes.')
PY
