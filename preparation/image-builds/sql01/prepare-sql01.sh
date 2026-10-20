#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run this script with sudo.'; exit 1; }
[[ $(hostname -s) == sql01 ]] || { echo 'Expected sql01.'; exit 1; }
apt-get update
apt-get install -y realmd sssd-ad sssd-tools adcli libnss-sss libpam-sss krb5-user samba-common-bin packagekit mariadb-server
systemctl enable --now mariadb
echo 'Preparation complete. Domain join and remote database access are not configured yet.'
