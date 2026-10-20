#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && $(hostname -s) == sql01 ]] || { echo 'Run with sudo on sql01 only.'; exit 1; }
umask 077
record=$(mktemp -d /var/backups/summit-sql01-inventory-XXXXXXXX)
export SQL01_INVENTORY_RECORD="$record"
python3 - <<'PY'
import json, os, pathlib, subprocess
root = pathlib.Path(os.environ['SQL01_INVENTORY_RECORD'])
checks = {
 'os':['cat','/etc/os-release'],
 'addresses':['ip','-j','address'],
 'disk':['df','-h','/'],
 'realm':['realm','list'],
 'domain_trust':['adcli','testjoin','--domain=corp.summit.test'],
 'sssd_validation':['sssctl','config-check'],
 'services':['systemctl','show','mariadb','ssh','sssd','ufw','apparmor','auditd','unattended-upgrades','-p','Id','-p','ActiveState','-p','UnitFileState'],
 'listeners':['ss','-lntup'],
 'firewall':['ufw','status','verbose'],
 'apparmor':['aa-status'],
 'packages':['dpkg-query','-W'],
 'holds':['apt-mark','showhold'],
 'sudo_jwang':['sudo','-l','-U','jwang'],
 'sudo_alex':['sudo','-l','-U','alex.admin@corp.summit.test'],
 'sudo_taylor':['sudo','-l','-U','taylor.admin@corp.summit.test'],
 'ssh_validation':['/usr/sbin/sshd','-t'],
 'ssh_effective':['/usr/sbin/sshd','-T','-C','user=jwang,host=sql01,addr=10.77.50.1'],
 'db_variables':['mariadb','--batch','--skip-column-names','-e',"SHOW GLOBAL VARIABLES WHERE Variable_name IN ('version','bind_address','require_secure_transport','have_ssl','local_infile','secure_file_priv','general_log','log_bin','skip_name_resolve');"],
 'db_accounts':['mariadb','--batch','--skip-column-names','-e','SELECT User,Host,plugin FROM mysql.user ORDER BY User,Host;'],
 'db_schemas':['mariadb','--batch','--skip-column-names','-e','SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_ROWS FROM information_schema.tables WHERE TABLE_SCHEMA NOT IN (\'mysql\',\'information_schema\',\'performance_schema\',\'sys\') ORDER BY TABLE_SCHEMA,TABLE_NAME;'],
 'db_grants':['mariadb','--batch','--skip-column-names','-e','SELECT GRANTEE,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.USER_PRIVILEGES; SELECT GRANTEE,TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES; SELECT GRANTEE,TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES;'],
}
report = {'machine':'sql01','record':str(root),'read_only':True,'checks':{}}
for name, args in checks.items():
 try:
  p = subprocess.run(args, text=True, capture_output=True, timeout=35)
  report['checks'][name] = {'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except (OSError,subprocess.TimeoutExpired) as e:
  report['checks'][name] = {'error':str(e)}
private = root/'inventory.json'
private.write_text(json.dumps(report,indent=2)+'\n')
# No passwords, password hashes, keytabs, or database contents are collected.
public = pathlib.Path('/home/jwang/sql01-competition-inventory.json')
if public.exists() or public.is_symlink():
 raise SystemExit('Inventory retained privately at '+str(private)+'; existing export was preserved.')
fd = os.open(public,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as f: f.write(json.dumps(report,indent=2)+'\n')
import pwd
user = pwd.getpwnam('jwang')
os.chown(public,user.pw_uid,user.pw_gid)
print('Inventory saved: '+str(public))
print('Private evidence: '+str(private))
PY
