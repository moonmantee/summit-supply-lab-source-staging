#!/usr/bin/env bash
# Rehearse and stage three harmless fixtures; preserve all unrelated jobs/units.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
source "$source_dir/stage_common.sh"
[[ -f /home/jwang/shop01-baseline.json && -f /home/jwang/shop01-probe-validation.json ]] || { echo 'Complete baseline collection and root probe validation first.'; exit 1; }
bash "$source_dir/validate-probes.sh"
for path in /opt/summit-shop-training /var/lib/summit-shop-markers /etc/cron.d/summit-shop-marker /etc/systemd/system/summit-shop-marker.service; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing scenario path; refusing overwrite: $path"; exit 1; }
done
if getent passwd summit_shop_marker >/dev/null; then echo 'Runner already exists; refusing overwrite.'; exit 1; fi
python3 - "$source_dir" <<'PY'
import json,pathlib,sys
p=pathlib.Path('/home/jwang/shop01-probe-validation.json'); d=json.loads(p.read_text())
assert len(d['checks'])==40 and d['total_points']==100
assert all(i['status']=='PASS' for i in d['checks'] if i['id'] in (38,39,40)), 'Original persistence state must be clean'
sys.path.insert(0,str(pathlib.Path(sys.argv[1])/'probes'))
import persistence
assert all(persistence.check(i) for i in (38,39,40))
import web
status,body=web.fetch('/')
assert status==200 and web.healthy_catalog(body), 'Storefront baseline must work before staging'
assert web.fetch('/order-history.php')[0]==200, 'Order history must remain available'
PY
backup_dir=$(mktemp -d /var/backups/summit-shop01-persistence-XXXXXXXX)
install -d -m 700 "$backup_dir/probes"
cp "$source_dir/probes/"*.py "$backup_dir/probes/"
chown -R root:root "$backup_dir"
printf '%s\n' 'Original fixture paths and runner absent.' > "$backup_dir/original-state.txt"
created_runner=0
rollback() {
  systemctl disable --now summit-shop-marker.service >/dev/null 2>&1 || true
  rm -f -- /etc/cron.d/summit-shop-marker /etc/systemd/system/summit-shop-marker.service || return 1
  systemctl daemon-reload || return 1
  # These exact new scenario paths were verified absent before this batch.
  rm -rf -- /opt/summit-shop-training /var/lib/summit-shop-markers || return 1
  if [[ $created_runner == 1 ]] && getent passwd summit_shop_marker >/dev/null; then userdel summit_shop_marker || return 1; fi
  created_runner=0
}
enable_rollback_trap
install -d -m 755 /opt/summit-shop-training
useradd --system --home-dir /var/lib/summit-shop-markers --shell /usr/sbin/nologin summit_shop_marker
created_runner=1
install -d -o summit_shop_marker -g summit_shop_marker -m 750 /var/lib/summit-shop-markers
for kind in cron systemd; do
  cat > "/opt/summit-shop-training/$kind-marker.sh" <<EOF
#!/usr/bin/env sh
printf '%s\n' '$kind training marker' >> /var/lib/summit-shop-markers/events.log
EOF
  chmod 755 "/opt/summit-shop-training/$kind-marker.sh"
done
install -m 755 /usr/bin/true /opt/summit-shop-training/suid-marker
cat > "$backup_dir/marker.service" <<'EOF'
[Unit]
Description=Unauthorized harmless Summit training marker
[Service]
Type=oneshot
RemainAfterExit=yes
User=summit_shop_marker
Group=summit_shop_marker
ExecStart=/opt/summit-shop-training/systemd-marker.sh
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/summit-shop-markers
[Install]
WantedBy=multi-user.target
EOF
assert_state() {
  python3 - "$backup_dir" "$1" "$2" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); expected=sys.argv[3]=='PASS'; sys.path.insert(0,str(root/'probes'))
import persistence
states={str(i):persistence.check(i) for i in (38,39,40)}
assert all(v is expected for v in states.values()), 'Persistence rehearsal state mismatch'
with (root/'rehearsal.jsonl').open('a') as f: f.write(json.dumps({'phase':sys.argv[2],'states':states})+'\n')
print(sys.argv[2]+': '+sys.argv[3]+' for 38,39,40')
PY
}
plant() {
  printf '%s\n' '*/5 * * * * summit_shop_marker /opt/summit-shop-training/cron-marker.sh' > /etc/cron.d/summit-shop-marker
  chmod 644 /etc/cron.d/summit-shop-marker
  install -m 644 "$backup_dir/marker.service" /etc/systemd/system/summit-shop-marker.service
  systemctl daemon-reload
  systemctl enable --now summit-shop-marker.service
  chmod 4755 /opt/summit-shop-training/suid-marker
}
repair() {
  rm -f -- /etc/cron.d/summit-shop-marker
  systemctl disable --now summit-shop-marker.service
  rm -f -- /etc/systemd/system/summit-shop-marker.service
  systemctl daemon-reload
  chmod 755 /opt/summit-shop-training/suid-marker
}
assert_state secure PASS
plant
assert_state planted FAIL
repair
assert_state repaired PASS
rollback
created_runner=0
assert_state restored-original PASS
# Recreate only the same inert fixtures for the final participant image.
useradd --system --home-dir /var/lib/summit-shop-markers --shell /usr/sbin/nologin summit_shop_marker
created_runner=1
install -d -m 755 /opt/summit-shop-training
install -d -o summit_shop_marker -g summit_shop_marker -m 750 /var/lib/summit-shop-markers
for kind in cron systemd; do
  cat > "/opt/summit-shop-training/$kind-marker.sh" <<EOF
#!/usr/bin/env sh
printf '%s\n' '$kind training marker' >> /var/lib/summit-shop-markers/events.log
EOF
  chmod 755 "/opt/summit-shop-training/$kind-marker.sh"
done
install -m 755 /usr/bin/true /opt/summit-shop-training/suid-marker
plant
assert_state final-planted FAIL
systemctl is-active --quiet apache2
systemctl is-active --quiet ssh
bash "$source_dir/validate-probes.sh"
trap - ERR
install -o jwang -g jwang -m 600 "$backup_dir/rehearsal.jsonl" /home/jwang/shop01-persistence-rehearsal.jsonl
echo "Three persistence objectives staged and rehearsed. Private evidence: $backup_dir"
echo 'Production scoring remains unchanged. Root collector backup and VMware snapshot remain recovery options.'
