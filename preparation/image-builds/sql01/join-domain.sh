#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo from sql01.'; exit 1; }
[[ $(hostname -s) == sql01 ]] || { echo 'Expected sql01.'; exit 1; }
ip -4 address show dev ens33 | grep -q 'inet 10.77.50.20/24' || { echo 'Expected isolated SQL address.'; exit 1; }
getent passwd jwang >/dev/null
getent hosts dc01.corp.summit.test | grep -q '^10.77.40.10 ' || { echo 'Check domain DNS.'; exit 1; }
umask 077
backup=$(mktemp -d /var/backups/sql01-domain-XXXXXXXX)
for item in /etc/sssd /etc/krb5.conf /etc/ssh/sshd_config /etc/pam.d /etc/systemd/timesyncd.conf.d; do
    if [[ -e $item ]]; then cp -a --parents "$item" "$backup/"; fi
done
mkdir -p /etc/systemd/timesyncd.conf.d
printf '[Time]\nNTP=10.77.50.1\nFallbackNTP=\n' > /etc/systemd/timesyncd.conf.d/90-summit-lab.conf
systemctl enable --now systemd-timesyncd
systemctl restart systemd-timesyncd
echo 'Waiting up to 90 seconds for the lab clock...'
for ((attempt=0; attempt<45; attempt++)); do
    [[ $(timedatectl show -p NTPSynchronized --value) == yes ]] && break
    sleep 2
done
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || { echo 'Clock not synchronized; domain join not attempted. Ask organizer to inspect NTP.'; exit 1; }
if ! realm list --name-only | grep -Fxq corp.summit.test; then
    echo 'Enter the CORP Administrator password at the domain join prompt (not your local jwang password).'
    realm join --client-software=sssd --membership-software=adcli --user=Administrator corp.summit.test
fi
# Local recovery remains governed by the existing local account configuration.
# Permit only the two named privileged IT identities; no domain sudo grants.
realm deny --all --realm=corp.summit.test
realm permit --realm=corp.summit.test alex.admin@corp.summit.test taylor.admin@corp.summit.test
pam-auth-update --enable mkhomedir
sssctl config-check
adcli testjoin --domain=corp.summit.test
id alex.admin@corp.summit.test
id taylor.admin@corp.summit.test
realm list
systemctl is-active mariadb ssh sssd
echo "Domain setup complete. Backup: $backup"
echo 'jwang remains the local sudo/recovery account. Domain users have no new sudo grant.'
echo 'Organizer must verify fresh allowed/denied logins and database access next.'
