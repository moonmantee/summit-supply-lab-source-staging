#!/usr/bin/env bash
# Run from the guest console with sudo. Does not plant weaknesses or modify policy.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run this script with sudo.'; exit 1; }
[[ $(. /etc/os-release; echo "$ID") == almalinux ]]
[[ $(hostname -s) == workstation01 ]]
backup_dir="/var/backups/summit-workstation01-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$backup_dir"
backup_targets=()
for path in /etc/ssh/sshd_config /etc/ssh/sshd_config.d /etc/pam.d /etc/authselect /etc/security /etc/sudoers /etc/sudoers.d /etc/firewalld /etc/selinux/config /etc/audit /etc/dnf /etc/yum.repos.d /etc/systemd/journald.conf /etc/systemd/journald.conf.d /etc/profile.d /etc/gdm/custom.conf; do
  [[ ! -e "$path" ]] || backup_targets+=("${path#/}")
done
tar -C / -czf "$backup_dir/configuration.tar.gz" "${backup_targets[@]}"
chmod 600 "$backup_dir/configuration.tar.gz"
export SUMMIT_BASELINE_BACKUP="$backup_dir"
python3 - <<'PY'
import datetime,json,os,pathlib,subprocess,tempfile

def run(argv):
    try:
        p=subprocess.run(argv,text=True,capture_output=True,timeout=30)
        return {"exit":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {"exit":None,"error":str(e)}

commands={
 "os":["cat","/etc/os-release"],
 "kernel":["uname","-r"],
 "identity":["id","jwang"],
 "local_users":["getent","-s","files","passwd"],
 "wheel":["getent","group","wheel"],
 "domain":["realm","list"],
 "authselect":["authselect","current"],
 "authselect_integrity":["authselect","check"],
 "sshd_jwang":["/usr/sbin/sshd","-T","-C","user=jwang,host=workstation01,addr=10.77.10.50"],
 "sshd_root":["/usr/sbin/sshd","-T","-C","user=root,host=workstation01,addr=10.77.10.50"],
 "sudo_jwang":["sudo","-l","-U","jwang"],
 "sudo_syntax":["visudo","-c"],
 "selinux":["getenforce"],
 "kernel_arguments":["cat","/proc/cmdline"],
 "firewall_runtime":["firewall-cmd","--list-all-zones"],
 "firewall_permanent":["firewall-cmd","--permanent","--list-all-zones"],
 "active_zones":["firewall-cmd","--get-active-zones"],
 "services":["systemctl","list-unit-files","--no-pager"],
 "timers":["systemctl","list-timers","--all","--no-pager"],
 "scorer":["systemctl","show","summit-aeacus","-p","ActiveState","-p","SubState","-p","MainPID","-p","NRestarts"],
 "audit_status":["auditctl","-s"],
 "audit_rules":["auditctl","-l"],
 "packages":["rpm","-q","firefox","gedit","cups","avahi","dnf-automatic","audit","sudo","sssd","authselect"],
 "filesystem_modes":["stat","-c","%a %U:%G %n","/tmp","/etc/profile.d","/home/jwang/.ssh","/home/jwang/.ssh/authorized_keys"],
 "desktop_directory":["ls","-ld","/home/jwang/Desktop"],
 "firefox_profiles":["find","/home/jwang/.mozilla/firefox","-maxdepth","2","-type","f","-name","prefs.js"],
}
data={"collected_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "backup_directory":os.environ["SUMMIT_BASELINE_BACKUP"],
      "snapshot":"User confirmed snapshot; name and restore test not independently verified",
      "checks":{name:run(argv) for name,argv in commands.items()}}
# Read only explicitly selected non-secret policy files. Never read shadow,
# SSH private keys, SSSD configuration secrets, Firefox logins, or key databases.
allowed=["/etc/security/pwquality.conf","/etc/security/faillock.conf",
         "/etc/security/pwhistory.conf","/etc/pam.d/system-auth",
         "/etc/pam.d/password-auth","/etc/selinux/config",
         "/etc/systemd/journald.conf","/etc/dnf/automatic.conf",
         "/etc/gdm/custom.conf"]
data["policy_files"]={}
for filename in allowed:
    p=pathlib.Path(filename)
    if p.is_file():
        data["policy_files"][filename]=p.read_text(errors="replace")
out=pathlib.Path("/home/jwang/summit-workstation01-baseline.json")
if out.exists():
    raise SystemExit("Previous inventory exists: preserve it before repeating the collector")
fd=os.open(str(out),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2)
import pwd
account=pwd.getpwnam("jwang")
os.chown(out,account.pw_uid,account.pw_gid)
print("Inventory saved:",out)
print("Root-only configuration backup:",data["backup_directory"])
PY
echo 'Baseline collection complete. No weaknesses planted.'
