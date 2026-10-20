#!/usr/bin/env bash
# Local PAM objectives7–10; preserve SSSD and sudo-group recovery exemption.
set -euo pipefail
umask 077
export LC_ALL=C
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
for name in summit_pam_probe summit_pam_recovery_probe; do
  ! getent passwd "$name" >/dev/null || { echo 'PAM probe identity collision'; exit 1; }
done
command -v pamtester >/dev/null
command -v faillock >/dev/null
[[ -f /home/jwang/shop01-baseline.json ]] || exit 1
bash "$source_dir/validate-probes.sh"
backup_dir=$(mktemp -d /var/backups/summit-shop01-pam-XXXXXXXX)
install -d -m 700 "$backup_dir/pam" "$backup_dir/probes"
cp -a /etc/pam.d/common-{auth,account,password} "$backup_dir/pam/"
cp -a /etc/security/faillock.conf /etc/security/opasswd "$backup_dir/"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
cp "$source_dir/validate-pam-functional.py" "$backup_dir/"
getfacl -p /etc/passwd /etc/shadow /etc/group /etc/gshadow > "$backup_dir/account.acl"
cleanup_users() {
  local name
  for name in summit_pam_probe summit_pam_recovery_probe; do
    if getent passwd "$name" >/dev/null; then
      faillock --user "$name" --reset || return 1
      userdel "$name" || return 1
    fi
  done
  cp -a "$backup_dir/opasswd" /etc/security/opasswd || return 1
  setfacl --restore="$backup_dir/account.acl" || return 1
}
rollback() {
  cp -a "$backup_dir/pam/"common-* /etc/pam.d/ || return 1
  cp -a "$backup_dir/faillock.conf" /etc/security/faillock.conf || return 1
  cleanup_users || return 1
}
enable_rollback_trap
trap 'summit_on_error 130' INT
trap 'summit_on_error 143' TERM
configure() {
  python3 - "$backup_dir" "$1" <<'PY'
import pathlib,re,sys
root=pathlib.Path(sys.argv[1]); secure=sys.argv[2]=='secure'
original=(root/'pam/common-password').read_text()
quality=('password requisite pam_pwquality.so retry=1 local_users_only minlen='+('14' if secure else '6')+
         ' enforcing='+('1' if secure else '0')+' dcredit=0 ucredit=0 lcredit=0 ocredit=0')
text,count=re.subn(r'(?m)^password\s+requisite\s+pam_pwquality[.]so[^\n]*$',quality,original)
assert count==1, 'Unknown baseline pwquality layout'
history='password [success=ok default=1] pam_localuser.so\npassword required pam_pwhistory.so use_authtok remember='+('5' if secure else '0')
text,count=re.subn(r'(?m)^(password\s+\[success=2 default=ignore\]\s+pam_unix[.]so[^\n]*)$',lambda m:history+'\n'+m[1].replace('obscure ','') ,text)
assert count==1, 'Unknown baseline Unix/SSSD password flow'
pathlib.Path('/etc/pam.d/common-password').write_text(text)
auth=(root/'pam/common-auth').read_text(); account=(root/'pam/common-account').read_text()
if secure:
    auth,count=re.subn(r'(?m)^auth\s+\[success=2 default=ignore\]\s+pam_unix[.]so nullok$',
        'auth [success=ok default=1] pam_localuser.so\nauth required pam_faillock.so preauth silent\nauth [success=3 default=ignore] pam_unix.so nullok',auth)
    assert count==1, 'Unknown baseline Unix authentication flow'
    auth,count=re.subn(r'(?m)^auth\s+\[success=1 default=ignore\]\s+pam_sss[.]so use_first_pass$',
        'auth [success=2 default=ignore] pam_sss.so use_first_pass\nauth [default=die] pam_faillock.so authfail',auth)
    assert count==1, 'Unknown baseline SSSD authentication flow'
    auth,count=re.subn(r'(?m)^(auth\s+required\s+pam_permit[.]so[^\n]*)$',r'auth required pam_faillock.so authsucc\n\1',auth)
    assert count==1
    account='account required pam_faillock.so\n'+account
pathlib.Path('/etc/pam.d/common-auth').write_text(auth)
pathlib.Path('/etc/pam.d/common-account').write_text(account)
pathlib.Path('/etc/security/faillock.conf').write_text('deny=5\nfail_interval=900\nunlock_time=900\nlocal_users_only\nadmin_group=sudo\n')
PY
}
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes'))
import pam,web
states={str(i):pam.check(i) for i in (7,8,9,10)}
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
assert all(v is (sys.argv[3]=='PASS') for v in states.values()), 'PAM rehearsal mismatch: '+str(states)
from common import active,run
assert active('ssh') and active('sssd')
assert all('sudo' in run(['id','-nG',u]).split() for u in ('jwang','summit_editor'))
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body) and web.fetch('/order-history.php')[0]==200
print(sys.argv[2]+': '+sys.argv[3]+' for 7–10; business services PASS')
PY
}
functional() {
  python3 "$backup_dir/validate-pam-functional.py" "$1" "$backup_dir/functional-$2.json"
  setfacl --restore="$backup_dir/account.acl"
}
useradd -M -N -g nogroup -d /nonexistent -s /bin/bash summit_pam_probe
useradd -M -N -g nogroup -G sudo -d /nonexistent -s /bin/bash summit_pam_recovery_probe
configure secure
assert_state secure PASS
functional secure secure
configure planted
assert_state planted FAIL
functional planted planted
configure secure
assert_state repaired PASS
functional secure repaired
rollback
for file in common-auth common-account common-password; do cmp -s "$backup_dir/pam/$file" "/etc/pam.d/$file"; done
echo 'Original PAM, lockout settings and password-history data restored.'
configure planted
assert_state final-planted FAIL
bash "$source_dir/validate-probes.sh"
trap - ERR INT TERM
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-pam-rehearsal.jsonl
echo "Four local PAM objectives staged/rehearsed. Private recovery: $backup_dir"
echo 'Production scoring unchanged. Verify a fresh authorized domain login before release.'
