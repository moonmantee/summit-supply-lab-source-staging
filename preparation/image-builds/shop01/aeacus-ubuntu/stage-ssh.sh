#!/usr/bin/env bash
# Objectives 12–16. Retain jwang keys/password and all PAM/domain configuration.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
config=/etc/ssh/sshd_config.d/00-000-summit-training.conf
keydir=/home/summit_editor/.ssh
metadata=/var/lib/summit-shop01/private.json
[[ ! -e $config && ! -L $config && ! -e $keydir && ! -L $keydir ]] || { echo 'SSH fixture collision'; exit 1; }
[[ -f $metadata && ! -L $metadata && $(stat -c '%U %a' "$metadata") == 'root 600' ]] || exit 1
[[ $(getent passwd summit_editor | cut -d: -f6) == /home/summit_editor ]] || exit 1
/usr/sbin/sshd -t
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-ssh-XXXXXXXX)
cp -a /etc/ssh "$backup_dir/original-ssh"
cp -a "$metadata" "$backup_dir/original-private.json"
getfacl -p /home/summit_editor > "$backup_dir/original-home.acl"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
rollback() {
  rm -f -- "$config" || return 1
  [[ ! -L $keydir ]] || return 1
  rm -rf -- "$keydir" || return 1
  cp -a "$backup_dir/original-private.json" "$metadata" || return 1
  setfacl --restore="$backup_dir/original-home.acl" || return 1
  /usr/sbin/sshd -t || return 1
  systemctl reload ssh || return 1
}
enable_rollback_trap
ssh-keygen -q -t ed25519 -N '' -C approved-shop-editor -f "$backup_dir/approved-key"
ssh-keygen -q -t ed25519 -N '' -C unauthorized-training-fixture -f "$backup_dir/unauthorized-key"
awk '{print "localhost " $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub > "$backup_dir/known-hosts"
setup_keys() {
  install -d -o summit_editor -g summit_editor -m 700 "$keydir"
  install -o summit_editor -g summit_editor -m 600 "$backup_dir/approved-key.pub" "$keydir/authorized_keys"
  python3 - "$metadata" "$backup_dir" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); root=pathlib.Path(sys.argv[2]); data=json.loads(p.read_text())
assert 'approved_key_blob' not in data and 'unauthorized_key_blob' not in data
data['approved_key_blob']=(root/'approved-key.pub').read_text().split()[1]
data['unauthorized_key_blob']=(root/'unauthorized-key.pub').read_text().split()[1]
p.write_text(json.dumps(data))
PY
}
configure() {
  local mode=$1
  if [[ $mode == secure ]]; then
    printf 'PermitRootLogin no\nPermitEmptyPasswords no\nAllowUsers jwang summit_editor\n' > "$config"
    cat "$backup_dir/approved-key.pub" > "$keydir/authorized_keys"
    chmod 700 "$keydir"
    chmod 600 "$keydir/authorized_keys"
  else
    printf 'PermitRootLogin yes\nPermitEmptyPasswords yes\nAllowUsers jwang summit_editor contractor_lab\n' > "$config"
    cat "$backup_dir/approved-key.pub" "$backup_dir/unauthorized-key.pub" > "$keydir/authorized_keys"
    # These excessive read/list permissions remain compatible with StrictModes:
    # do not make authorized administrator key authentication unusable.
    chmod 755 "$keydir"
    chmod 644 "$keydir/authorized_keys"
  fi
  chown summit_editor:summit_editor "$keydir/authorized_keys"
  chmod 644 "$config"
  /usr/sbin/sshd -t
  systemctl reload ssh
}
verify_login() {
  local fixture=$1 expected=$2
  python3 - "$backup_dir" "$fixture" "$expected" <<'PY'
import pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1])
cmd=['ssh','-F','/dev/null','-i',str(root/(sys.argv[2]+'-key')),
     '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5',
     '-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519',
     '-o','UserKnownHostsFile='+str(root/'known-hosts'),'summit_editor@localhost','id -un']
p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
if sys.argv[3]=='ALLOW': assert p.returncode==0 and p.stdout.strip()=='summit_editor', 'Approved editor SSH failed'
else: assert p.returncode==255 and 'Permission denied' in p.stderr, 'Unauthorized key was not denied'
print(sys.argv[2]+': actual SSH '+sys.argv[3])
PY
}
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes'))
import access,web
states={str(i):access.check(i) for i in range(12,17)}
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
bad=[i for i,v in states.items() if v is not (sys.argv[3]=='PASS')]
assert not bad, 'SSH rehearsal mismatch: '+','.join(bad)
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body) and web.fetch('/order-history.php')[0]==200
from common import active,run,setting
assert active('sssd')
assert setting(access.ssh_configs('summit_editor')[0],'strictmodes')=='yes'
assert setting(access.ssh_configs('summit_editor')[0],'trustedusercakeys')=='none', 'External SSH CA needs separate validation'
sudo=run(['sudo','-ll','-U','jwang'])
assert 'RunAsUsers: ALL' in sudo and '\tALL' in sudo, 'Recovery sudo lost'
print(sys.argv[2]+': '+sys.argv[3]+' for 12–16; business/recovery checks PASS')
PY
}
setup_keys
configure secure
verify_login approved ALLOW
verify_login unauthorized DENY
assert_state secure PASS
configure planted
verify_login approved ALLOW
verify_login unauthorized ALLOW
assert_state planted FAIL
configure secure
verify_login approved ALLOW
verify_login unauthorized DENY
assert_state repaired PASS
rollback
cmp -s "$metadata" "$backup_dir/original-private.json"
echo 'Original SSH/key/metadata state restored.'
setup_keys
configure planted
verify_login approved ALLOW
verify_login unauthorized ALLOW
assert_state final-planted FAIL
# Keep only the untrusted public marker; its disposable private key has no role
# after proving actual behavior. Approved key remains private for organizer use.
rm -f -- "$backup_dir/unauthorized-key"
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-ssh-rehearsal.jsonl
echo "Five SSH objectives staged/rehearsed. Private recovery: $backup_dir"
echo 'Production scoring unchanged. Fresh organizer/domain login verification remains required.'
