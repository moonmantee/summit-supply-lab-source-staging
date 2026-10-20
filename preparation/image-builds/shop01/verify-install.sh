#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0
apache2ctl configtest
systemctl is-active apache2
systemctl is-active ssh
systemctl is-active summit-aeacus
test -s /opt/aeacus/assets/ScoringReport.html
test ! -f /opt/aeacus/scoring.conf
openssl verify -CAfile /etc/ssl/certs/summit-shop01.crt /etc/ssl/certs/summit-shop01.crt
python3 - <<'PY'
import ssl, urllib.request
context = ssl.create_default_context(cafile='/etc/ssl/certs/summit-shop01.crt')
with urllib.request.urlopen('https://10.77.30.10/',context=context,timeout=10) as response:
    body=response.read().decode()
    assert response.status == 200
    for token in ['SUMMIT-SHOP01-BASELINE-V1','SUM-101','SUM-102','SUM-103']:
        assert token in body, token
print('HTTPS hostname/certificate and catalog content verified.')
PY
