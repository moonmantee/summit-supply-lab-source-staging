"""Live access checks. Credentials stay on score01 and are never printed."""
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.request

secrets={}
for line in Path('/home/jwang/summit-portal/portal-state/INITIAL-PORTAL-CREDENTIALS.txt').read_text().splitlines():
    key,_,value=line.partition(': '); secrets[key]=value

def client(base):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(path,payload=None,csrf=None):
        headers={'Origin':base}
        if payload is not None: headers['Content-Type']='application/json'
        if csrf: headers['X-Portal-CSRF']=csrf
        req=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        try:
            with opener.open(req,timeout=10) as response: return response.status,response.read(),dict(response.headers)
        except urllib.error.HTTPError as error: return error.code,error.read(),dict(error.headers)
    return request

team=client('http://10.77.70.10:8080'); admin=client('http://127.0.0.1:8767')
assert team('/portal/api/state')[0]==401
assert team('/portal/api/login',{'username':'admin','password':secrets['Organizer password']})[0]==403
assert team('/portal/api/login',{'username':'team','password':secrets['Team password']})[0]==200
status,body,_=team('/portal/api/state'); state=json.loads(body)
assert status==200 and state['role']=='team' and state['event']['state']=='STOPPED'
assert state['injects']==[] and state['scores']['inject_points']==0
status,body,headers=team('/portal/scoreboard/index.html')
assert status==200 and b'Competition 1' in body and b'control-panel' not in body and b'summit-control-token' not in body
assert headers.get('X-Frame-Options')=='SAMEORIGIN'
assert team('/portal/scoreboard/history.html')[0]==200
assert team('/portal/files/README.docx')[1].startswith(b'PK')
assert admin('/portal/api/login',{'username':'admin','password':secrets['Organizer password']})[0]==200
status,body,_=admin('/portal/api/state'); private=json.loads(body)
assert status==200 and len(private['injects'])==6
assert sum(card['points'] for card in private['injects'])==100
assert all(card['automatic'] and card['released_at'] is None for card in private['injects'])
assert [card['code'] for card in private['injects'] if card['needs_configuration']]==['I03']
attachments=[a for card in private['injects'] for a in card['attachments']]
assert len(attachments)==5
for attachment in attachments:
    assert team('/portal/attachments/'+str(attachment['id']))[0]==404
    assert admin('/portal/attachments/'+str(attachment['id']))[0]==200
for key in ['Team password','Organizer password']:
    assert secrets[key].encode() not in body
ftp_password=json.loads(Path('/home/jwang/summit-portal/portal-state/resources/ftp-account.json').read_text())['password']
assert ftp_password.encode() not in body
assert team('/portal/api/logout',{},state['csrf'])[0]==200
assert admin('/portal/api/logout',{},private['csrf'])[0]==200
print(json.dumps({'live_verified':True,'team_portal':'HTTP 200','existing_scoreboard':'HTTP 200; read-only team view','public_organizer_login':'HTTP 403','private_organizer_login':'HTTP 200','word_readme':'download verified','private_drafts':6,'completion_points':100,'protected_task_attachments':5,'mail_draft':'configuration required','released_tasks':0,'event_state':state['event']['state']}))
