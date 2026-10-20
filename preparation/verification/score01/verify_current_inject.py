import http.cookiejar
import json
from pathlib import Path
import urllib.request
base='http://10.77.70.10:8080'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
values=dict(line.split(': ',1) for line in Path('/home/jwang/summit-portal/portal-state/INITIAL-PORTAL-CREDENTIALS.txt').read_text().splitlines())
request=urllib.request.Request(base+'/portal/api/login',data=json.dumps({'username':'team','password':values['Team password']}).encode(),headers={'Origin':base,'Content-Type':'application/json'})
with opener.open(request,timeout=10) as response: response.read()
with opener.open(base+'/portal/api/state',timeout=10) as response: state=json.load(response)
assert state['event']['state']=='RUNNING'
assert [c['code'] for c in state['injects']]==['I01']
first=state['injects'][0]
assert first['status']=='Grace period' and first['scoring_starts_at']-first['released_at']==1800
assert first['service_id'] not in {s['service_id'] for s in state['services']}
assert 'inject_template' not in state['settings']
print({'team_verified':True,'event_id':state['event']['id'],'visible_injects':['I01'],'status':first['status'],'no_inject_service_checks_during_grace':True})
request=urllib.request.Request(base+'/portal/api/logout',data=b'{}',headers={'Origin':base,'Content-Type':'application/json','X-Portal-CSRF':state['csrf']})
with opener.open(request,timeout=10) as response: response.read()
