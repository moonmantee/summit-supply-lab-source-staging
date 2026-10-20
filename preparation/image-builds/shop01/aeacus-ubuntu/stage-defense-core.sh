#!/usr/bin/env bash
# Objectives 19,22,23,24; no firewall, PAM, SSH or SSSD changes.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
profile=/etc/apparmor.d/usr.sbin.rsyslogd
journal=/etc/systemd/journald.conf.d/zzzz-summit-training.conf
updates=/etc/apt/apt.conf.d/99zzzz-summit-training
for path in "$journal" "$updates" /etc/apparmor.d/force-complain/usr.sbin.rsyslogd /etc/apparmor.d/disable/usr.sbin.rsyslogd; do
  [[ ! -e $path && ! -L $path ]] || { echo "Fixture collision: $path"; exit 1; }
done
[[ -f /home/jwang/shop01-baseline.json && -f $profile ]] || exit 1
systemctl is-active --quiet rsyslog
systemctl is-active --quiet apt-daily-upgrade.timer
[[ $(systemctl is-enabled apt-daily-upgrade.timer) == enabled ]] || exit 1
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-defense-core-XXXXXXXX)
cp -a "$profile" "$backup_dir/original-profile"
apt-mark showhold > "$backup_dir/original-holds"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
packages=(apache2 apache2-bin apache2-data apache2-utils)
for package in "${packages[@]}"; do
  [[ $(dpkg-query -W -f='${db:Status-Status}' "$package") == installed ]] || exit 1
done
restore_holds() {
  local package
  for package in "${packages[@]}"; do
    if grep -Fxq "$package" "$backup_dir/original-holds"; then
      apt-mark hold "$package" >/dev/null || return 1
    else
      apt-mark unhold "$package" >/dev/null || return 1
    fi
  done
}
rollback() {
  cp -a "$backup_dir/original-profile" "$profile" || return 1
  apparmor_parser -r "$profile" || return 1
  rm -f -- "$journal" "$updates" || return 1
  systemctl restart systemd-journald || return 1
  restore_holds || return 1
}
enable_rollback_trap
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes'))
import defense,web
states={str(i):defense.check(i) for i in (19,22,23,24)}
phase=sys.argv[2]; expected=sys.argv[3]
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':phase,'states':states})+'\n')
if expected!='RECORD':
    bad=[i for i,v in states.items() if v is not (expected=='PASS')]
    assert not bad, 'Defense rehearsal mismatch: '+','.join(bad)
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body), 'Catalog failed'
assert web.fetch('/order-history.php')[0]==200, 'Order history failed'
from common import active
assert all(active(u) for u in ('ssh','sssd','rsyslog')), 'Required service failed'
print(phase+': '+expected+' for 19,22,23,24; business services PASS')
PY
}
configure() {
  local phase=$1
  python3 - "$backup_dir/original-profile" "$profile" "$phase" <<'PY'
import pathlib,re,sys
text=pathlib.Path(sys.argv[1]).read_text()
pattern=r'(?m)^(profile rsyslogd /usr/sbin/rsyslogd flags=\()([^)]*)(\) \{)$'
def update(m):
    flags=[f.strip() for f in m[2].split(',') if f.strip() and f.strip()!='complain']
    if sys.argv[3]=='planted': flags.append('complain')
    return m[1]+','.join(flags)+m[3]
text,count=re.subn(pattern,update,text)
assert count==1, 'Unexpected rsyslog profile declaration'
pathlib.Path(sys.argv[2]).write_text(text)
PY
  apparmor_parser -r "$profile"
  install -d -m 755 /etc/systemd/journald.conf.d
  if [[ $phase == secure ]]; then
    printf '[Journal]\nStorage=persistent\n' > "$journal"
    printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > "$updates"
    apt-mark unhold "${packages[@]}" >/dev/null
    systemd-tmpfiles --create --prefix /var/log/journal
    systemctl restart systemd-journald
    journalctl --flush
  else
    printf '[Journal]\nStorage=volatile\n' > "$journal"
    printf 'APT::Periodic::Update-Package-Lists "0";\nAPT::Periodic::Unattended-Upgrade "0";\n' > "$updates"
    apt-mark hold apache2 >/dev/null
    systemctl restart systemd-journald
  fi
  chmod 644 "$journal" "$updates"
}
assert_state original RECORD
configure secure
assert_state secure PASS
configure planted
assert_state planted FAIL
configure secure
assert_state repaired PASS
rollback
assert_state restored-original RECORD
python3 - "$backup_dir/rehearsal.jsonl" <<'PY'
import json,pathlib,sys
rows=[json.loads(line) for line in pathlib.Path(sys.argv[1]).read_text().splitlines()]
assert rows[0]['states']==rows[-1]['states'], 'Original defense state mismatch'
PY
configure planted
assert_state final-planted FAIL
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-defense-core-rehearsal.jsonl
echo "Four defense objectives staged/rehearsed. Private backup: $backup_dir"
echo 'Production scoring unchanged.'
