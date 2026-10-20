#!/usr/bin/env bash
# Fetch authenticated prerequisites only; no package install or policy staging.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
[[ -f /home/jwang/shop01-baseline.json ]] || exit 1
backup_dir=$(mktemp -d /var/backups/summit-shop01-packages-XXXXXXXX)
cp -a /etc/apt "$backup_dir/original-apt"
dpkg-query -W -f='${Package}\t${Version}\t${db:Status-Status}\n' > "$backup_dir/original-packages.txt"
apt-mark showhold > "$backup_dir/original-holds.txt"
python3 - <<'PY'
import pathlib,re
paths=[pathlib.Path('/etc/apt/sources.list'),*pathlib.Path('/etc/apt/sources.list.d').glob('*.list'),*pathlib.Path('/etc/apt/sources.list.d').glob('*.sources')]
for p in paths:
    if not p.exists(): continue
    text='\n'.join(l.split('#',1)[0] for l in p.read_text().splitlines())
    assert not re.search(r'(?i)trusted\s*=\s*yes|trusted\s*:\s*yes|allow-insecure\s*=\s*yes|allow-insecure\s*:\s*yes',text), 'Repository trust override requires investigation'
assert pathlib.Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg').is_file()
PY
options=(-o APT::Get::AllowUnauthenticated=false
         -o Acquire::AllowInsecureRepositories=false
         -o Acquire::AllowDowngradeToInsecureRepositories=false
         -o Acquire::Retries=0 -o Acquire::http::Timeout=15
         -o APT::Update::Error-Mode=any)
if ! timeout 180 apt-get "${options[@]}" update > "$backup_dir/update.log" 2>&1; then
  echo "Authenticated package index refresh failed. Private diagnostic: $backup_dir/update.log"
  exit 1
fi
if ! timeout 120 apt-get "${options[@]}" --download-only --no-install-recommends --no-remove -y install auditd pamtester > "$backup_dir/download.log" 2>&1; then
  echo "Authenticated prerequisite download failed. Private diagnostic: $backup_dir/download.log"
  exit 1
fi
apt-cache policy auditd pamtester > "$backup_dir/package-policy.txt"
printf '%s\n' "$backup_dir" > /home/jwang/shop01-package-preparation.txt
chown jwang:jwang /home/jwang/shop01-package-preparation.txt
chmod 600 /home/jwang/shop01-package-preparation.txt
echo "Authenticated auditd/PAM-test packages downloaded. Private evidence: $backup_dir"
echo 'No packages installed, repositories changed, or weaknesses planted by this preparation.'
