#!/usr/bin/env bash
# Account objectives 1–6 and 11. No PAM or SSH configuration changes.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
names=(summit_employee summit_support summit_editor contractor_lab summit_rootalias)
for name in "${names[@]}"; do
  ! getent passwd "$name" >/dev/null || { echo "Identity collision: $name"; exit 1; }
  ! getent group "$name" >/dev/null || { echo "Group collision: $name"; exit 1; }
  if [[ $name == summit_employee || $name == summit_support || $name == summit_editor ]]; then
    [[ ! -e /home/$name && ! -L /home/$name ]] || { echo "Home collision: $name"; exit 1; }
  fi
done
metadata=/var/lib/summit-shop01
grant=/etc/sudoers.d/summit-training-support
[[ ! -e $metadata && ! -L $metadata && ! -e $grant && ! -L $grant ]] || { echo 'Scenario metadata/grant collision'; exit 1; }
[[ $(id -nG nobody) != *sudo* && -f /home/jwang/shop01-baseline.json ]] || exit 1
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-users-XXXXXXXX)
cp -a /etc/passwd /etc/shadow /etc/group /etc/gshadow "$backup_dir/"
getfacl -p /etc/passwd /etc/shadow /etc/group /etc/gshadow > "$backup_dir/original.acl"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
rollback() {
  local name
  rm -f -- "$grant" || return 1
  if id -nG nobody | tr ' ' '\n' | grep -Fxq sudo; then gpasswd -d nobody sudo >/dev/null || return 1; fi
  for name in summit_rootalias contractor_lab summit_employee summit_support summit_editor; do
    if getent passwd "$name" >/dev/null; then
      if [[ $name == summit_rootalias ]]; then
        # UID 0 is busy because root is running; remove only this exact alias.
        userdel -f "$name" || return 1
      else
        userdel "$name" || return 1
      fi
    fi
    if getent group "$name" >/dev/null; then groupdel "$name" || return 1; fi
    # Only approved accounts create homes. Locked fixtures use /nonexistent;
    # preserve any unrelated pre-existing contractor/root-alias home paths.
    if [[ $name == summit_employee || $name == summit_support || $name == summit_editor ]]; then
      [[ ! -L /home/$name ]] || return 1
      rm -rf -- "/home/$name" || return 1
    fi
  done
  [[ ! -L $metadata ]] || return 1
  rm -rf -- "$metadata" || return 1
  setfacl --restore="$backup_dir/original.acl" || return 1
  visudo -c >/dev/null || return 1
}
enable_rollback_trap
python3 - "$backup_dir" <<'PY'
import json,pathlib,secrets,subprocess,sys
root=pathlib.Path(sys.argv[1]); data={}
for name in ('summit_employee','summit_support','summit_editor','employee_repaired'):
    password=secrets.token_urlsafe(24)
    hashed=subprocess.run(['openssl','passwd','-6','-stdin'],input=password+'\n',capture_output=True,text=True,check=True).stdout.strip()
    data[name]={'password':password,'hash':hashed}
password='Lab'+secrets.token_hex(2)+'!'
hashed=subprocess.run(['openssl','passwd','-6','-stdin'],input=password+'\n',capture_output=True,text=True,check=True).stdout.strip()
data['employee_planted']={'password':password,'hash':hashed}
(root/'credentials.json').write_text(json.dumps(data))
PY
set_credential() {
  python3 - "$backup_dir/credentials.json" "$1" "$2" <<'PY'
import json,pathlib,subprocess,sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
subprocess.run(['chpasswd','-e'],input=sys.argv[2]+':'+data[sys.argv[3]]['hash']+'\n',text=True,check=True)
PY
  # Account tools may rewrite files: retain the separately staged metadata state.
  setfacl --restore="$backup_dir/original.acl"
}
setup_required() {
  local name
  for name in summit_employee summit_support summit_editor; do
    useradd -m -s /bin/bash "$name"
    chmod 750 "/home/$name"
    set_credential "$name" "$name"
  done
  usermod -aG sudo summit_editor
  install -d -m 700 "$metadata"
  python3 - "$backup_dir/credentials.json" "$metadata/private.json" <<'PY'
import json,pathlib,sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
pathlib.Path(sys.argv[2]).write_text(json.dumps({'planted_employee_hash':data['employee_planted']['hash']}))
PY
  chmod 600 "$metadata/private.json"
  chage -M 90 summit_employee
  setfacl --restore="$backup_dir/original.acl"
}
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes'))
import access,web
states={str(i):access.check(i) for i in (1,2,3,4,5,6,11)}
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
bad=[i for i,v in states.items() if v is not (sys.argv[3]=='PASS')]
assert not bad, 'Account rehearsal mismatch: '+','.join(bad)
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body) and web.fetch('/order-history.php')[0]==200
from common import active,run
assert all(active(u) for u in ('ssh','sssd','apache2'))
sudo=run(['sudo','-ll','-U','jwang'])
assert 'RunAsUsers: ALL' in sudo and '\tALL' in sudo, 'Recovery sudo lost'
assert 'sudo' in run(['id','-nG','summit_editor']).split()
print(sys.argv[2]+': '+sys.argv[3]+' for 1–6,11; business/recovery checks PASS')
PY
}
plant() {
  useradd -M -N -g nogroup -d /nonexistent -s /usr/sbin/nologin contractor_lab
  useradd -M -N -o -u 0 -g root -d /nonexistent -s /usr/sbin/nologin summit_rootalias
  usermod -aG sudo summit_employee
  usermod -aG sudo nobody
  printf 'summit_support ALL=(root) NOPASSWD: /usr/bin/true\n' > "$grant"
  chmod 440 "$grant"
  visudo -c >/dev/null
  set_credential summit_employee employee_planted
  chage -M 99999 summit_employee
  setfacl --restore="$backup_dir/original.acl"
}
repair() {
  userdel contractor_lab
  userdel -f summit_rootalias
  gpasswd -d summit_employee sudo >/dev/null
  gpasswd -d nobody sudo >/dev/null
  rm -f -- "$grant"
  set_credential summit_employee employee_repaired
  chage -M 90 summit_employee
  setfacl --restore="$backup_dir/original.acl"
  visudo -c >/dev/null
}
setup_required
assert_state secure PASS
plant
assert_state planted FAIL
repair
assert_state repaired PASS
rollback
python3 - <<'PY'
import pathlib
targets={'summit_employee','summit_support','summit_editor','contractor_lab','summit_rootalias'}
assert not targets.intersection(l.split(':')[0] for l in pathlib.Path('/etc/passwd').read_text().splitlines())
assert not pathlib.Path('/var/lib/summit-shop01').exists()
PY
echo 'Original account state restored; prior permission objectives retained.'
setup_required
plant
assert_state final-planted FAIL
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-users-rehearsal.jsonl
echo "Seven account objectives staged/rehearsed. Private recovery and fictional credentials: $backup_dir"
echo 'Production scoring unchanged. Do not publish the private credentials file.'
