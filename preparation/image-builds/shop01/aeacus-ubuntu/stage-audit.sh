#!/usr/bin/env bash
# Install cached authenticated prerequisites, then rehearse objectives20–21.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
[[ -f /home/jwang/shop01-package-preparation.txt ]] || exit 1
rules=/etc/audit/rules.d/70-summit-training.rules
[[ ! -e $rules && ! -L $rules ]] || { echo 'Audit-rule fixture collision'; exit 1; }
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-audit-XXXXXXXX)
dpkg-query -W -f='${Package}\t${Version}\t${db:Status-Status}\n' > "$backup_dir/packages-before.txt"
if ! apt-get -o APT::Get::AllowUnauthenticated=false --no-download --no-install-recommends --no-remove -y install auditd pamtester > "$backup_dir/install.log" 2>&1; then
  echo "Prerequisite installation failed; no audit policy staged. Private diagnostic: $backup_dir/install.log"
  exit 1
fi
# The new required tools are retained. Capture the installed audit baseline
# before weakening it; do not uninstall dependencies during rollback.
systemctl enable --now auditd
auditctl -s > "$backup_dir/original-status.txt"
auditctl -l > "$backup_dir/original-runtime.txt"
python3 - "$backup_dir" <<'PY'
import pathlib,re,sys
root=pathlib.Path(sys.argv[1]); status=(root/'original-status.txt').read_text()
assert re.search(r'(?m)^enabled\s+1$',status), 'Audit disabled or immutable: cannot safely rehearse'
assert (root/'original-runtime.txt').read_text().strip()=='No rules', 'Existing runtime rules require separate preservation review'
PY
cp -a /etc/audit "$backup_dir/original-audit"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
rollback() {
  rm -f -- "$rules" || return 1
  cp -a "$backup_dir/original-audit/." /etc/audit/ || return 1
  systemctl enable --now auditd || return 1
  auditctl -D || return 1
  augenrules --load || return 1
}
enable_rollback_trap
secure() {
  cat > "$rules" <<'EOF'
-w /etc/passwd -p wa -k summit_accounts
-w /etc/group -p wa -k summit_accounts
-w /etc/shadow -p wa -k summit_accounts
-w /etc/sudoers -p wa -k summit_privilege
-w /etc/sudoers.d -p wa -k summit_privilege
EOF
  chmod 600 "$rules"
  systemctl enable --now auditd
  augenrules --load
}
remove_rules() {
  rm -f -- "$rules"
  auditctl -D
  augenrules --load
}
plant() {
  remove_rules
  systemctl disable --now auditd
}
assert_state() {
  python3 - "$backup_dir" "$1" "$2" "$3" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes'))
import defense,web
states={str(i):defense.check(i) for i in (20,21)}
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
assert states=={'20':sys.argv[3]=='PASS','21':sys.argv[4]=='PASS'}, 'Audit rehearsal mismatch'
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body) and web.fetch('/order-history.php')[0]==200
from common import active
assert active('ssh') and active('sssd')
print(sys.argv[2]+': 20 '+sys.argv[3]+', 21 '+sys.argv[4]+'; business services PASS')
PY
}
assert_state installed-baseline PASS FAIL
secure
assert_state secure PASS PASS
remove_rules
assert_state rules-only-planted PASS FAIL
plant
assert_state planted FAIL FAIL
secure
assert_state repaired PASS PASS
rollback
assert_state restored-installed-baseline PASS FAIL
plant
assert_state final-planted FAIL FAIL
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-audit-rehearsal.jsonl
echo "Two audit objectives staged/rehearsed. Private installed-baseline recovery: $backup_dir"
echo 'auditd/pamtester remain installed. Production scoring unchanged.'
