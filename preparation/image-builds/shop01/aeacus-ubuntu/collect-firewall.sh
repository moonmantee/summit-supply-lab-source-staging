#!/usr/bin/env bash
# Read-only firewall inventory and private recovery copy; no rule changes.
set -euo pipefail
umask 077
[[ $(id -u) == 0 && $(hostname -s) == shop01 ]] || { echo 'Run with sudo on shop01.'; exit 1; }
backup_dir=$(mktemp -d /var/backups/summit-shop01-firewall-baseline-XXXXXXXX)
cp -a /etc/ufw "$backup_dir/ufw"
cp -a /etc/default/ufw "$backup_dir/default-ufw"
iptables-save > "$backup_dir/iptables.rules"
ip6tables-save > "$backup_dir/ip6tables.rules"
python3 - "$backup_dir" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1])
def run(args): return subprocess.run(args,capture_output=True,text=True,check=True,timeout=15).stdout
data={'backup':str(root),'ufw_status':run(['ufw','status','verbose']),
      'all_tables4':(root/'iptables.rules').read_text(),
      'all_tables6':(root/'ip6tables.rules').read_text(),
      'runtime4':run(['iptables-save','-t','filter']),
      'runtime6':run(['ip6tables-save','-t','filter']),
      'persistent4':(root/'ufw/user.rules').read_text(),
      'persistent6':(root/'ufw/user6.rules').read_text(),
      'before4':(root/'ufw/before.rules').read_text(),
      'before6':(root/'ufw/before6.rules').read_text(),
      'ufw_config':(root/'ufw/ufw.conf').read_text(),
      'default_config':(root/'default-ufw').read_text()}
pathlib.Path('/home/jwang/shop01-firewall-baseline.json').write_text(json.dumps(data,indent=2)+'\n')
PY
chown jwang:jwang /home/jwang/shop01-firewall-baseline.json
chmod 600 /home/jwang/shop01-firewall-baseline.json
echo "Firewall inventory and exact private rollback captured: $backup_dir"
echo 'Read-only collection: runtime/persistent firewall unchanged.'
