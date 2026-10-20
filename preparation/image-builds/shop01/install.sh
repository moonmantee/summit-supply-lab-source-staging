#!/usr/bin/env bash
# Run locally in Ubuntu with sudo after reviewing this file.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run: sudo bash install.sh'; exit 1; }
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
BUILD=$PWD
test -f site/index.html
test -f scoring.conf
test -f vendor/aeacus-linux-v2.1.1.zip
test "$(uname -m)" = x86_64
if test -e /opt/aeacus || test -e /var/www/summit; then
  echo 'An existing Summit/Aeacus installation was found. Stop and review before replacing it.'
  exit 1
fi
printf '%s  %s\n' 'bd75e05505bd1a1e288b0453a4611ad88f6794dd54063db16485e0328c69f149' 'vendor/aeacus-linux-v2.1.1.zip' | sha256sum --check
BACKUP="/var/backups/summit-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$BACKUP"
tar -czf "$BACKUP/apache-before.tar.gz" /etc/apache2 /var/www/html 2>/dev/null
cp -a /etc/ssh/sshd_config "$BACKUP/sshd_config"
cp -a /etc/ssh/sshd_config.d "$BACKUP/sshd_config.d"
printf '%s\n' "$BACKUP" > "$BUILD/backup-location.txt"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y apache2 openssl unzip python3
install -d -m 755 /var/www/summit
install -m 644 site/index.html /var/www/summit/index.html
if test -e /etc/ssl/private/summit-shop01.key || test -e /etc/ssl/certs/summit-shop01.crt; then
  echo 'An existing Summit certificate was found. Review before replacing it.'
  exit 1
fi
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -keyout /etc/ssl/private/summit-shop01.key \
  -out /etc/ssl/certs/summit-shop01.crt \
  -subj '/CN=shop01.corp.summit.test/O=Summit Supply Practice' \
  -addext 'subjectAltName=DNS:shop01.corp.summit.test,DNS:shop01,IP:10.77.30.10' \
  -addext 'basicConstraints=critical,CA:FALSE' \
  -addext 'keyUsage=critical,digitalSignature,keyEncipherment' \
  -addext 'extendedKeyUsage=serverAuth'
chmod 600 /etc/ssl/private/summit-shop01.key
chmod 644 /etc/ssl/certs/summit-shop01.crt
install -m 644 summit-shop.conf /etc/apache2/sites-available/summit-shop.conf
a2enmod ssl
a2ensite summit-shop
a2dissite 000-default
if ! apache2ctl configtest; then
  a2dissite summit-shop
  a2ensite 000-default
  echo 'Apache syntax check failed; original default site re-enabled. No reload performed.'
  exit 1
fi
systemctl reload apache2
# Preserve jwang key/password login; only deny direct root/empty-password login.
install -d -m 755 /etc/ssh/sshd_config.d
test ! -e /etc/ssh/sshd_config.d/00-summit.conf
printf '%s\n' 'PermitRootLogin no' 'PermitEmptyPasswords no' > /etc/ssh/sshd_config.d/00-summit.conf
chmod 644 /etc/ssh/sshd_config.d/00-summit.conf
if ! /usr/sbin/sshd -t; then
  mv /etc/ssh/sshd_config.d/00-summit.conf "$BACKUP/00-summit-rejected.conf"
  echo 'SSH config rejected; new snippet removed. No reload performed.'
  exit 1
fi
systemctl reload ssh
# The official release helper performs unrelated cleanup; use specific subcommands only.
EXTRACT=$(mktemp -d)
unzip -q vendor/aeacus-linux-v2.1.1.zip -d "$EXTRACT"
install -d -m 755 /opt/aeacus
cp -a "$EXTRACT/aeacus-linux/assets" /opt/aeacus/
install -m 700 "$EXTRACT/aeacus-linux/aeacus" /opt/aeacus/aeacus
install -m 700 "$EXTRACT/aeacus-linux/phocus" /opt/aeacus/phocus
install -m 600 scoring.conf /opt/aeacus/scoring.conf
install -m 600 ReadMe.conf /opt/aeacus/ReadMe.conf
printf '%s\n' 'SUMMIT-PRACTICE-01' > /opt/aeacus/TeamID.txt
chmod 644 /opt/aeacus/TeamID.txt
cd /opt/aeacus
./aeacus version
./aeacus --verbose check
./aeacus --verbose readme
./aeacus --verbose score
./aeacus --verbose encrypt
test -s /opt/aeacus/scoring.dat
chmod 600 /opt/aeacus/scoring.dat
# Organizer master remains in Windows shop01-build, not on the defended machine.
rm -- /opt/aeacus/scoring.conf
install -m 644 "$BUILD/summit-aeacus.service" /etc/systemd/system/summit-aeacus.service
systemctl daemon-reload
systemctl enable --now summit-aeacus
install -d -o jwang -g jwang -m 755 /home/jwang/Desktop
ln -s /opt/aeacus/assets/ScoringReport.html /home/jwang/Desktop/Summit-Scoring-Report.html
ln -s /opt/aeacus/assets/ReadMe.html /home/jwang/Desktop/Summit-ReadMe.html
sleep 3
bash "$BUILD/verify-install.sh"
printf '\nInstalled. Backup: %s\nWebsite: https://10.77.30.10/\nScoring report: /opt/aeacus/assets/ScoringReport.html\n' "$BACKUP"
echo 'The HTTPS certificate is self-signed for this private lab. Browser trust setup is a separate step.'
echo 'After external verification, remove the uploaded build directory; the organizer master is on Windows.'
