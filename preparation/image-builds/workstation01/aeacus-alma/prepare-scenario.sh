#!/usr/bin/env bash
# Prepare scenario resources only. No authentication-policy weakening and no
# persistence activation. New local identities start locked and expired.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run with sudo.'; exit 1; }
[[ $(hostname -s) == workstation01 ]] || { echo 'Wrong machine.'; exit 1; }
source /etc/os-release
[[ $ID == almalinux && $VERSION_ID == 9.8 ]] || { echo 'Wrong operating system.'; exit 1; }
source_dir=/home/jwang/aeacus-setup
[[ -f $source_dir/scenario-assets/app.conf && -f $source_dir/evidence/scenario-events.txt ]] || { echo 'Missing organizer assets.'; exit 1; }
# Abort before any mutation if a name/path already belongs to another setup.
for name in summit-keyuser summit-admin summit-unknown summit-departed summit-employee summit-auditor; do
  if getent passwd "$name" >/dev/null; then
    echo "Account already exists: $name. No preparation performed."
    exit 1
  fi
done
for path in /opt/summit-evidence /etc/summit-workstation /usr/local/lib/summit-training /usr/local/share/summit-games /etc/profile.d/summit-workstation.sh /home/jwang/Desktop/Forensics.txt; do
  [[ ! -e $path && ! -L $path ]] || { echo "Scenario path already exists: $path. No preparation performed."; exit 1; }
done
cd "$source_dir"
python3 - <<'PY'
import hashlib,json,pathlib
expected=json.loads(pathlib.Path('artifact-hashes.json').read_text())
assert len(expected)==12,'Incomplete asset inventory'
for name,digest in expected.items():
    assert pathlib.Path(name).name==name,'Invalid asset name'
    assert hashlib.sha256((pathlib.Path('scenario-assets')/name).read_bytes()).hexdigest()==digest,'Asset hash mismatch: '+name
PY
install -d -o root -g root -m 755 /opt/summit-evidence /etc/summit-workstation /usr/local/lib/summit-training /usr/local/share/summit-games
install -o root -g root -m 644 evidence/systemd-marker.sh evidence/scenario-events.txt /opt/summit-evidence/
install -o root -g root -m 644 scenario-assets/app.conf /etc/summit-workstation/app.conf
install -o root -g root -m 644 scenario-assets/summit-workstation.sh /etc/profile.d/summit-workstation.sh
install -o jwang -g jwang -m 600 scenario-assets/Forensics.txt /home/jwang/Desktop/Forensics.txt
for name in summit-keyuser summit-admin summit-unknown summit-departed summit-employee summit-auditor; do
  useradd --create-home --shell /sbin/nologin --expiredate 1970-01-02 "$name"
  passwd --lock "$name" >/dev/null
done
restorecon -R /opt/summit-evidence /etc/summit-workstation /usr/local/lib/summit-training /usr/local/share/summit-games /etc/profile.d/summit-workstation.sh
printf '%s\n' 'Scenario resources prepared. Training accounts are locked, expired, and use nologin.' 'No persistence activated; SSH, SSSD, PAM, firewall, SELinux, and production scoring were not changed.'
