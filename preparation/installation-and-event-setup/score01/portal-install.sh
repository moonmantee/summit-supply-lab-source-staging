#!/bin/bash
# Install only on organizer score01; preserve scoring history and lifecycle state.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run this installer with sudo on score01.'; exit 1; }
ip -4 address show | grep -q '10.77.70.10/24' || { echo 'Expected score01 at 10.77.70.10/24.'; exit 1; }
id jwang >/dev/null
src=$(cd -- "$(dirname -- "$0")" && pwd)
dst=/home/jwang/summit-portal
score=/home/jwang/summit-scoring
nginx_site=/etc/nginx/sites-available/summit-downloads
[[ -f $score/state/results.sqlite3 && -f $nginx_site ]] || { echo 'Existing scoring database and downloads site are required.'; exit 1; }
for f in scorer.py shop_probe.py inject_services.py portal_scoreboard.py prepare_inject_resources.py scoreboard.css scoreboard.js portal_server.py portal_store.py portal-injects.json portal-web/index.html portal-web/app.js portal-web/style.css README.md README.docx summit-team-portal.service; do
  [[ -f $src/$f ]] || { echo "Missing package file: $f"; exit 1; }
done
backup=/var/backups/summit-portal-$(date -u +%Y%m%dT%H%M%SZ)-$$
install -d -m 700 "$backup"
cp -a "$nginx_site" "$backup/summit-downloads"
cp -a "$score/scorer.py" "$backup/scorer.py"
cp -a "$score/config.json" "$backup/config.json"
for f in portal_store.py inject_services.py shop_probe.py; do
  if [[ -f $score/$f ]]; then cp -a "$score/$f" "$backup/$f"; fi
done
uid=$(id -u jwang)
userctl() { runuser -u jwang -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user "$@"; }
wait_portal() {
  local url=$1 attempt status
  for attempt in {1..10}; do
    status=$(curl --noproxy '*' --silent --show-error --output /dev/null --write-out '%{http_code}' --connect-timeout 2 --max-time 5 -H 'Host: 10.77.70.10:8080' "$url") || status=000
    if [[ $status == 200 ]]; then return 0; fi
    if [[ $attempt != 10 ]]; then sleep 1; fi
  done
  echo "Portal health check failed after 10 attempts: $url (HTTP $status)." >&2
  return 1
}
was_active=0
was_enabled=0
timer_active=0
backup_ready=0
if userctl is-active --quiet summit-team-portal.service; then was_active=1; fi
if userctl is-active --quiet summit-check.timer; then timer_active=1; fi
if userctl is-enabled --quiet summit-team-portal.service; then was_enabled=1; fi
if [[ -f /home/jwang/.config/systemd/user/summit-team-portal.service ]]; then
  cp -a /home/jwang/.config/systemd/user/summit-team-portal.service "$backup/previous-unit"
fi
rollback() {
  result=$?
  if [[ $result != 0 ]]; then
    set +e
    userctl stop summit-team-portal.service
    userctl stop summit-check.timer summit-check.service
    cp -a "$backup/scorer.py" "$score/scorer.py"
    cp -a "$backup/config.json" "$score/config.json"
    for f in portal_store.py inject_services.py shop_probe.py; do
      if [[ -f $backup/$f ]]; then cp -a "$backup/$f" "$score/$f"; else rm -f "$score/$f"; fi
    done
    cp -a "$backup/summit-downloads" "$nginx_site"
    if [[ $backup_ready == 1 ]]; then
      # Disable while the unit still exists so systemd removes its enable symlink.
      if [[ $was_enabled == 0 ]]; then userctl disable summit-team-portal.service; fi
      if [[ -d $dst ]]; then mv "$dst" "$backup/failed-portal"; fi
      if [[ -d $backup/previous-portal ]]; then cp -a "$backup/previous-portal" "$dst"; fi
      if [[ -f $backup/previous-unit ]]; then
        cp -a "$backup/previous-unit" /home/jwang/.config/systemd/user/summit-team-portal.service
      else
        rm -f /home/jwang/.config/systemd/user/summit-team-portal.service
      fi
      userctl daemon-reload
      if [[ $was_enabled == 1 ]]; then userctl enable summit-team-portal.service; fi
    fi
    nginx -t && systemctl reload nginx
    if [[ $was_active == 1 ]]; then userctl start summit-team-portal.service; fi
    if [[ $timer_active == 1 ]]; then userctl start summit-check.timer; fi
    echo "Installation failed; prior portal and Nginx restored where present. Recovery records: $backup" >&2
  fi
  exit "$result"
}
trap rollback EXIT
userctl stop summit-check.timer summit-check.service
# Online SQLite backup preserves score history without resetting or changing event state.
/usr/bin/python3 - "$score/state/results.sqlite3" "$backup/results.sqlite3" <<'PY'
import sqlite3,sys
from contextlib import closing
with closing(sqlite3.connect(sys.argv[1])) as source, closing(sqlite3.connect(sys.argv[2])) as target:
    source.backup(target)
PY
# Quiesce the portal before copying SQLite and its related attachments.
if userctl is-active --quiet summit-team-portal.service; then
  was_active=1
  userctl stop summit-team-portal.service
fi
if [[ -d $dst ]]; then cp -a "$dst" "$backup/previous-portal"; fi
backup_ready=1
printf '%s\n' "$backup" > /var/backups/summit-portal-latest
install -d -o jwang -g jwang -m 700 "$dst" "$dst/portal-web" "$dst/inject-resources" "$dst/portal-state" "$dst/portal-state/files" /home/jwang/.config/systemd/user
for f in shipping-policy.txt health.json; do install -o jwang -g jwang -m 600 "$src/inject-resources/$f" "$dst/inject-resources/$f"; done
for f in shop_probe.py portal_server.py portal_store.py portal-injects.json inject_services.py portal_scoreboard.py prepare_inject_resources.py scoreboard.css scoreboard.js; do install -o jwang -g jwang -m 600 "$src/$f" "$dst/$f"; done
for f in scorer.py shop_probe.py portal_store.py inject_services.py; do install -o jwang -g jwang -m 600 "$src/$f" "$score/$f"; done
/usr/bin/python3 - "$score/config.json" "$dst/portal-state/portal.sqlite3" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); config=json.loads(p.read_text()); config['portal_database']=sys.argv[2]
p.write_text(json.dumps(config,indent=2)+'\n')
PY
# Reuse the existing scorer's configuration resolution without copying any secrets.
install -o jwang -g jwang -m 600 "$score/scorer.py" "$dst/scorer.py"
install -o jwang -g jwang -m 600 "$score/lifecycle.py" "$dst/lifecycle.py"
install -o jwang -g jwang -m 600 "$score/reporting.py" "$dst/reporting.py"
for f in index.html app.js style.css; do install -o jwang -g jwang -m 600 "$src/portal-web/$f" "$dst/portal-web/$f"; done
install -o jwang -g jwang -m 600 "$src/README.md" "$dst/portal-state/files/README.md"
install -o jwang -g jwang -m 600 "$src/README.docx" "$dst/portal-state/files/README.docx"
runuser -u jwang -- /usr/bin/python3 -m py_compile "$dst/portal_server.py" "$dst/portal_store.py"
if [[ ! -f $dst/portal-state/auth.json ]]; then
  runuser -u jwang -- /usr/bin/python3 "$dst/portal_server.py" init --scoring "$score/state/results.sqlite3" --config "$score/config.json"
fi
runuser -u jwang -- /usr/bin/python3 "$dst/portal_server.py" seed --scoring "$score/state/results.sqlite3" --config "$score/config.json"
runuser -u jwang -- /usr/bin/python3 "$dst/prepare_inject_resources.py"
install -o jwang -g jwang -m 600 "$src/summit-team-portal.service" /home/jwang/.config/systemd/user/summit-team-portal.service
# Add the portal location without changing existing download ACLs or proxy policy.
/usr/bin/python3 - "$nginx_site" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1]); text=p.read_text()
text=re.sub(r'\n    # BEGIN SUMMIT PORTAL\n.*?    # END SUMMIT PORTAL\n','\n',text,flags=re.S)
anchor='    server_tokens off;'
if text.count(anchor)!=1: raise SystemExit('Unrecognized Nginx site layout; preserved config, review manually.')
block='''
    # BEGIN SUMMIT PORTAL
    location = / { return 302 /portal/; }
    location = /portal { return 302 /portal/; }
    location /portal/ {
        client_max_body_size 3m;
        proxy_pass http://127.0.0.1:8767;
        proxy_set_header Host $http_host;
        proxy_set_header X-Portal-Proxied 1;
        proxy_set_header X-Portal-Client-IP $remote_addr;
        proxy_set_header X-Forwarded-For "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 20s;
    }
    location /downloads/ {
        alias /srv/summit-downloads/;
        limit_except GET { deny all; }
    }
    # END SUMMIT PORTAL
'''
p.write_text(text.replace(anchor,anchor+'\n'+block))
PY
if ! nginx -t; then
  cp -a "$backup/summit-downloads" "$nginx_site"
  echo "Nginx validation failed; original site restored. Backup: $backup" >&2
  exit 1
fi
userctl daemon-reload
userctl enable summit-team-portal.service
userctl restart summit-team-portal.service
if ! wait_portal http://127.0.0.1:8767/portal/; then
  cp -a "$backup/summit-downloads" "$nginx_site"
  echo "Portal backend failed. Original Nginx config restored; inspect user service logs. Backup: $backup" >&2
  exit 1
fi
systemctl reload nginx
if [[ $timer_active == 1 ]]; then userctl start summit-check.timer; fi
userctl is-active summit-team-portal.service summit-scoreboard.service
if [[ $timer_active == 1 ]]; then userctl is-active summit-check.timer; fi
# Nginx reload returns before every old worker has retired. Retry transient 404s.
wait_portal http://10.77.70.10:8080/portal/
echo "Team portal: http://10.77.70.10:8080/portal/"
echo 'Organizer: tunnel local port 8767 to score01:127.0.0.1:8767, then open http://127.0.0.1:8767/portal/#organizer'
echo 'Credential file: /home/jwang/summit-portal/portal-state/INITIAL-PORTAL-CREDENTIALS.txt (organizer-only).'
echo "Backup: $backup"
