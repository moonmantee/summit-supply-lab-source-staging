#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run: sudo bash /home/jwang/aeacus-setup/install.sh'; exit 1; }
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
[[ $(uname -m) == x86_64 ]]
[[ $(. /etc/os-release; echo "$ID") == almalinux ]]
if [[ -e /opt/aeacus || -e /etc/systemd/system/summit-aeacus.service ]]; then
  echo 'Existing Aeacus installation found; stop and inspect before replacing it.'
  exit 1
fi
printf '%s  %s\n' 'bd75e05505bd1a1e288b0453a4611ad88f6794dd54063db16485e0328c69f149' 'vendor/aeacus-linux-v2.1.1.zip' | sha256sum --check
unpack=$(mktemp -d)
trap 'rm -rf -- "$unpack"' EXIT
unzip -q vendor/aeacus-linux-v2.1.1.zip -d "$unpack"
install -d -m 755 /opt/aeacus
cp -a "$unpack/aeacus-linux/assets" /opt/aeacus/
chown -R root:root /opt/aeacus
find /opt/aeacus/assets -type d -exec chmod 755 {} +
find /opt/aeacus/assets -type f -exec chmod 644 {} +
install -m 700 "$unpack/aeacus-linux/aeacus" /opt/aeacus/aeacus
install -m 700 "$unpack/aeacus-linux/phocus" /opt/aeacus/phocus
install -m 600 scoring.conf /opt/aeacus/scoring.conf
install -m 600 ReadMe.conf /opt/aeacus/ReadMe.conf
printf '%s\n' 'SUMMIT-WORKSTATION01-BASELINE' > /opt/aeacus/TeamID.txt
chmod 644 /opt/aeacus/TeamID.txt
restorecon -RF /opt/aeacus
cd /opt/aeacus
./aeacus version
./aeacus --verbose check
./aeacus --verbose readme
./aeacus --verbose score
./aeacus --verbose encrypt
test -s scoring.dat
chmod 600 scoring.dat
rm -- scoring.conf
install -m 644 /home/jwang/aeacus-setup/summit-aeacus.service /etc/systemd/system/summit-aeacus.service
restorecon /etc/systemd/system/summit-aeacus.service
systemctl daemon-reload
systemctl enable --now summit-aeacus.service
install -d -o jwang -g jwang -m 755 /home/jwang/Desktop
for page in ScoringReport ReadMe; do
  target="/home/jwang/Desktop/Summit-${page}.desktop"
  [[ ! -e "$target" ]] || { echo "Shortcut already exists: $target"; exit 1; }
  cat > "$target" <<EOF
[Desktop Entry]
Type=Application
Name=Summit ${page}
Exec=firefox file:///opt/aeacus/assets/${page}.html
Icon=firefox
Terminal=false
EOF
  chown jwang:jwang "$target"
  chmod 755 "$target"
done
chmod 644 assets/ScoringReport.html assets/ReadMe.html
systemctl is-active summit-aeacus.service
echo 'Aeacus installation finished. Organizer will verify the report and runtime.'
