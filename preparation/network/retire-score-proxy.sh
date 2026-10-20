#!/bin/bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $(hostname -s) == score01 ]] || { echo 'Wrong host'; exit 1; }
ip -4 address show | grep -q '10.77.70.10/24' || exit 1
site=/etc/nginx/sites-available/summit-downloads
[[ -f $site ]] && grep -q 'proxy_pass http://127.0.0.1:8767;' "$site" || { echo 'Unexpected portal layout'; exit 1; }
backup=$(mktemp -d /var/backups/retire-score-proxy-XXXXXXXX)
chmod 700 "$backup"
cp -a "$site" "$backup/nginx-site"
cp -a /etc/squid "$backup/squid"
systemctl is-enabled squid > "$backup/squid-enabled" || true
systemctl is-active squid > "$backup/squid-active" || true
rollback() {
  cp -a "$backup/nginx-site" "$site"
  nginx -t && systemctl reload nginx
  systemctl unmask squid
  [[ ! -d $backup/downloads ]] || mv "$backup/downloads" /srv/summit-downloads
  [[ $(cat "$backup/squid-enabled") != enabled ]] || systemctl enable squid
  [[ $(cat "$backup/squid-active") != active ]] || systemctl start squid
  echo "Failed; rollback attempted. Recovery: $backup" >&2
}
trap rollback ERR
python3 - "$site" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text()
s=s.replace('    root /srv/summit-downloads;','    root /var/empty;').replace('    autoindex on;','    autoindex off;')
old='''    location /downloads/ {
        alias /srv/summit-downloads/;
        limit_except GET { deny all; }
    }'''
if s.count(old)!=1: raise SystemExit('Unexpected download location; no changes written')
s=s.replace(old,'    location /downloads/ { return 410; }')
old='    location / { limit_except GET { deny all; } }'
if s.count(old)!=1: raise SystemExit('Unexpected catch-all location; no changes written')
s=s.replace(old,'    location / { return 410; }')
p.write_text(s)
PY
nginx -t
systemctl reload nginx
curl --noproxy '*' --fail --silent --max-time 10 http://10.77.70.10:8080/portal/ >/dev/null
[[ $(curl --noproxy '*' --silent --max-time 10 -o /dev/null -w '%{http_code}' http://10.77.70.10:8080/downloads/) == 410 ]]
systemctl disable --now squid
systemctl mask squid
[[ ! -d /srv/summit-downloads ]] || mv /srv/summit-downloads "$backup/downloads"
trap - ERR
echo "Proxy retired; downloads removed from serving; portal preserved. Backup: $backup"
systemctl is-active nginx
runuser -u jwang -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active summit-team-portal.service summit-scoreboard.service summit-check.timer
