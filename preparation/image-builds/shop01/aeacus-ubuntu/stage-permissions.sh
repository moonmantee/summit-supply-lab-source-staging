#!/usr/bin/env bash
# Rehearse metadata weaknesses 25–29. No contents, passwords or keys are changed.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
[[ -f /home/jwang/shop01-baseline.json ]] || exit 1
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-permissions-XXXXXXXX)
paths=(/etc/shadow /etc/sudoers.d /etc/apache2/sites-available/summit-shop.conf /var/www/summit/index.php /etc/ssl/private /etc/ssl/private/summit-shop01.key)
getfacl -p "${paths[@]}" > "$backup_dir/original.acl"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
chown -R root:root "$backup_dir"
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes')); import permissions,web
expected=sys.argv[3]=='PASS'; states={str(i):permissions.check(i) for i in (25,26,27,28,29)}
bad=[i for i,v in states.items() if v is not expected]
assert not bad, 'Permissions rehearsal mismatch for objective(s): '+','.join(bad)
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body), 'Storefront must remain functional'
assert web.fetch('/order-history.php')[0]==200
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
print(sys.argv[2]+': '+sys.argv[3]+' for 25–29; storefront PASS')
PY
}
assert_state original PASS
rollback() { setfacl --restore="$backup_dir/original.acl"; }
enable_rollback_trap
plant() {
  chmod 644 /etc/shadow
  # Keep parsed sudo files themselves secure, preserving jwang's sudo. An
  # unsafe include parent exposes configuration to replacement/denial of service.
  setfacl -m u:nobody:rwx /etc/sudoers.d
  chmod 666 /etc/apache2/sites-available/summit-shop.conf
  chmod 666 /var/www/summit/index.php
  chmod o+x /etc/ssl/private
  chmod 644 /etc/ssl/private/summit-shop01.key
  visudo -c > "$backup_dir/sudo-syntax.txt"
  sudo -ll -U jwang > "$backup_dir/jwang-authorization.txt"
  python3 - "$backup_dir/jwang-authorization.txt" <<'PY'
import pathlib,sys
text=pathlib.Path(sys.argv[1]).read_text()
assert 'RunAsUsers: ALL' in text and 'Commands:' in text and '\tALL' in text, 'Recovery sudo grant must survive'
PY
  apache2ctl -t
  # Verify readability/writeability without reading secret contents.
  runuser -u nobody -- test -r /etc/shadow
  runuser -u nobody -- test -r /etc/ssl/private/summit-shop01.key
  runuser -u nobody -- test -w /etc/sudoers.d
  runuser -u nobody -- test -w /etc/apache2/sites-available/summit-shop.conf
  runuser -u www-data -- test -w /var/www/summit/index.php
}
plant
assert_state planted FAIL
rollback
assert_state repaired PASS
assert_state restored-original PASS
plant
assert_state final-planted FAIL
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-permissions-rehearsal.jsonl
echo "Five permissions objectives staged/rehearsed. Private original ACLs: $backup_dir/original.acl"
echo 'Production scoring unchanged. Recover exact metadata with sudo setfacl --restore=<private original.acl>.'
