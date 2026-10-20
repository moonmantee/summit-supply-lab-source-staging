#!/bin/bash
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Run with sudo.'; exit 1; }
case "$(hostname -s)" in
  score01) time_server=10.77.70.1 ;;
  shop01) time_server=10.77.30.1 ;;
  *) echo 'Unexpected host'; exit 1 ;;
esac
backup="/var/backups/summit-infra-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$backup"
install -d -m 755 /etc/systemd/timesyncd.conf.d
if test -f /etc/systemd/timesyncd.conf.d/90-summit.conf; then
  cp -p /etc/systemd/timesyncd.conf.d/90-summit.conf "$backup/"
fi
printf '[Time]\nNTP=%s\nFallbackNTP=\n' "$time_server" > /etc/systemd/timesyncd.conf.d/90-summit.conf
chmod 644 /etc/systemd/timesyncd.conf.d/90-summit.conf
systemctl enable --now systemd-timesyncd
systemctl restart systemd-timesyncd
if test "$(hostname -s)" = score01; then
  loginctl enable-linger jwang
  loginctl show-user jwang -p Linger
fi
echo "Prepared local time service. Backup: $backup"
