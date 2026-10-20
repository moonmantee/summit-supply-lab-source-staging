#!/usr/bin/env bash
# Objectives17–18; external observer proves actual permitted/denied traffic.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
[[ -f /home/jwang/shop01-firewall-baseline.json ]] || exit 1
[[ $(ufw status) == 'Status: inactive' ]] || { echo 'Firewall changed since inventory; refusing overwrite.'; exit 1; }
backup_dir=$(mktemp -d /var/backups/summit-shop01-firewall-XXXXXXXX)
cp -a /etc/ufw "$backup_dir/ufw"
cp -a /etc/default/ufw "$backup_dir/default-ufw"
iptables-save > "$backup_dir/iptables.rules"
ip6tables-save > "$backup_dir/ip6tables.rules"
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
python3 - "$backup_dir" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
sys.path.insert(0,str(root/'probes')); import defense
for name,ipv6 in (('iptables.rules',False),('ip6tables.rules',True)):
    text=(root/name).read_text()
    assert defense.inactive_firewall_baseline(text,ipv6), 'Existing runtime policy requires preservation review'
PY
listener_pid=''
listener_file=''
finish_notice() {
  printf '{"finished":true}\n' > /home/jwang/shop01-firewall-phase.json
  chown jwang:jwang /home/jwang/shop01-firewall-phase.json
  chmod 600 /home/jwang/shop01-firewall-phase.json
}
stop_listener() {
  if [[ -n $listener_pid ]]; then kill "$listener_pid" || return 1; wait "$listener_pid" || true; listener_pid=''; fi
  if [[ -n $listener_file ]]; then rm -f -- "$listener_file" || return 1; listener_file=''; fi
}
rollback() {
  ufw --force disable || return 1
  cp -a "$backup_dir/ufw/." /etc/ufw/ || return 1
  cp -a "$backup_dir/default-ufw" /etc/default/ufw || return 1
  iptables-restore < "$backup_dir/iptables.rules" || return 1
  ip6tables-restore < "$backup_dir/ip6tables.rules" || return 1
  stop_listener || return 1
  finish_notice || return 1
}
enable_rollback_trap
trap 'summit_on_error 130' INT
trap 'summit_on_error 143' TERM
bash "$source_dir/validate-probes.sh"
listener_file=$(mktemp /var/tmp/summit-firewall-marker-XXXXXXXX.py)
install -o root -g root -m 644 "$source_dir/firewall-marker.py" "$listener_file"
runuser -u nobody -- python3 "$listener_file" > "$backup_dir/listener.log" 2>&1 &
listener_pid=$!
python3 - <<'PY'
import socket,time
for _ in range(30):
    try:
        with socket.create_connection(('127.0.0.1',30303),1) as s: assert b'SUMMIT-FIREWALL-MARKER' in s.recv(80)
        break
    except OSError: time.sleep(.1)
else: raise RuntimeError('Temporary listener unavailable')
PY
remote_check() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,os,pathlib,pwd,stat,sys,time,uuid
root=pathlib.Path(sys.argv[1]); phase=sys.argv[2]; restricted=sys.argv[3]=='restricted'
nonce=uuid.uuid4().hex
request=pathlib.Path('/home/jwang/shop01-firewall-phase.json')
request.write_text(json.dumps({'nonce':nonce,'phase':phase,'created':time.time()})+'\n')
owner=pwd.getpwnam('jwang'); os.chown(request,owner.pw_uid,owner.pw_gid); request.chmod(0o600)
expected={'ssh_allowed':True,'http':True,'https':True,'marker':not restricted,'ssh_unapproved':not restricted}
ack=pathlib.Path('/home/jwang/shop01-firewall-ack.json')
deadline=time.monotonic()+180
print('Waiting for external firewall verification: '+phase,flush=True)
while time.monotonic()<deadline:
    try:
        st=ack.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=owner.pw_uid or st.st_size>8192: raise RuntimeError('Unsafe external evidence file')
        data=json.loads(ack.read_text())
        if data.get('nonce')==nonce:
            assert data.get('phase')==phase and abs(time.time()-data['created'])<180
            assert data.get('results')==expected, 'External allowed/denied firewall mismatch: '+str(data.get('results'))
            with (root/'remote.jsonl').open('a') as f: f.write(json.dumps(data)+'\n')
            print('Actual external flows verified: '+phase); break
    except (FileNotFoundError,json.JSONDecodeError): pass
    time.sleep(1)
else: raise RuntimeError('External observer timeout; original firewall will be restored')
PY
}
configure() {
  local mode=$1
  ufw --force reset > "$backup_dir/reset-$mode.log"
  # Retain standard connection tracking, ICMP and DHCP, but no unused multicast
  # discovery exposure in this server scenario.
  python3 - <<'PY'
import pathlib
for name in ('before.rules','before6.rules'):
    p=pathlib.Path('/etc/ufw')/name
    p.write_text('\n'.join(l for l in p.read_text().splitlines() if not (l.startswith('-A ') and '--dport' in l and any(' '+port+' ' in l for port in ('5353','1900'))))+'\n')
PY
  ufw default deny incoming
  ufw default allow outgoing
  ufw default deny routed
  ufw allow 80/tcp
  ufw allow 443/tcp
  if [[ $mode == secure ]]; then
    for source in 10.77.10.50 10.77.10.1 10.77.30.1 10.77.70.10; do ufw allow from "$source" to any port 22 proto tcp; done
  else
    ufw allow 22/tcp
    ufw allow 30303/tcp
  fi
  ufw --force enable
}
assert_state() {
  python3 - "$backup_dir" "$1" "$2" "$3" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes')); import defense,web
states={str(i):defense.check(i) for i in (17,18)}
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
assert states=={'17':sys.argv[3]=='PASS','18':sys.argv[4]=='PASS'}, 'Firewall rehearsal mismatch: '+str(states)
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body) and web.fetch('/order-history.php')[0]==200
from common import active
assert active('ssh') and active('sssd')
print(sys.argv[2]+': 17 '+sys.argv[3]+', 18 '+sys.argv[4]+'; business services PASS')
PY
}
if [[ ${1:-} == --diagnose ]]; then
  configure secure
  python3 - "$backup_dir" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'probes')); import defense
data=defense.collect(18)
data['persistent4']=pathlib.Path('/etc/ufw/user.rules').read_text()
data['persistent6']=pathlib.Path('/etc/ufw/user6.rules').read_text()
data['runtime4_safe']=defense.firewall_rules_safe(data['runtime4'])
data['runtime6_safe']=defense.firewall_rules_safe(data['runtime6'],True)
(root/'diagnostic.json').write_text(json.dumps(data,indent=2)+'\n')
print('Firewall diagnostic captured: persistent matches='+str(data['persistent_matches'])+', IPv4 safe='+str(data['runtime4_safe'])+', IPv6 safe='+str(data['runtime6_safe']))
PY
  install -o jwang -g jwang -m 600 "$backup_dir/diagnostic.json" /home/jwang/shop01-firewall-diagnostic.json
  rollback
  trap - ERR INT TERM
  echo 'Diagnostic complete; original firewall restored. No weaknesses staged.'
  exit 0
fi
remote_check original unrestricted
configure secure
assert_state secure PASS PASS
remote_check secure restricted
configure exposed
assert_state exposure-only PASS FAIL
remote_check exposure-only unrestricted
ufw --force disable
assert_state planted FAIL FAIL
configure secure
assert_state repaired PASS PASS
remote_check repaired restricted
# Restore original state, then start a fresh final planting (no live marker).
rollback
assert_state restored-original FAIL FAIL
configure exposed
ufw --force disable
assert_state final-planted FAIL FAIL
bash "$source_dir/validate-probes.sh"
finish_notice
trap - ERR INT TERM
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-firewall-rehearsal.jsonl
install -o jwang -g jwang -m 600 "$backup_dir/remote.jsonl" /home/jwang/shop01-firewall-remote.jsonl
echo "Two firewall objectives staged/rehearsed. Exact private recovery: $backup_dir"
echo 'Temporary listener stopped; production scoring unchanged.'
