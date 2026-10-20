#!/usr/bin/env bash
# Organizer preparation only: create a synthetic public training certificate.
# Does not add it to the trust store; private signing key is discarded.
set -euo pipefail
cd /home/jwang/aeacus-setup
umask 077
mkdir -p training-ca
if [[ ! -f training-ca/summit-training-ca.crt ]]; then
  trap 'rm -f -- training-ca/temporary-signing.key' EXIT
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout training-ca/temporary-signing.key \
    -out training-ca/summit-training-ca.crt \
    -subj '/CN=Summit Fictional Training CA/O=CyberPatriot Practice Only' \
    -addext 'basicConstraints=critical,CA:TRUE' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' >/dev/null 2>&1
fi
openssl x509 -in training-ca/summit-training-ca.crt -noout -fingerprint -sha256
