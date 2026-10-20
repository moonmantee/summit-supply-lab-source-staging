"""Run as unprivileged contact identity; checks the actual root broker over its socket."""
import os
import sys
sys.path.insert(0,'/opt/summit-caldera-fixtures')
from fixture_agent import local_request
assert os.geteuid()!=0,'Use the dedicated contact account'
assert not os.access('/etc/summit-caldera-fixtures/broker/client.key',os.R_OK)
assert not os.access('/etc/summit-red-agent/agent.json',os.R_OK)
reply=local_request({'status':True})
assert reply=={'healthy':True},reply
print('Dedicated contact UID, private broker credential isolation, actual systemd broker health and authorization TLS PASS')
