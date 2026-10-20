"""Root-local, read-only acceptance; never starts or dispatches an exercise."""
import json
import os
import pathlib
import pwd
import grp
import socket
import stat
import subprocess
import sys
import time
import urllib.request
import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Redirect denied')


def main():
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='red01':raise ValueError('Local red01 root required')
    credentials=json.loads(pathlib.Path('/etc/summit-caldera/credentials.json').read_text())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def api(path,key=None):
        req=urllib.request.Request('http://127.0.0.1:8888'+path,headers={'KEY':key} if key else {})
        try:
            with opener.open(req,timeout=5) as response:
                data=response.read(512*1024+1)
                if len(data)>512*1024:raise ValueError('Response exceeds limit')
                return response.status,json.loads(data)
        except urllib.error.HTTPError as error:return error.code,None
    value=None
    for attempt in range(20):
        try:
            code,value=api('/plugin/ccdc/api/bootstrap',credentials['red_api_key'])
            if code==200:break
        except (OSError,ValueError):pass
        time.sleep(.5)
    if not value or not value.get('ok'):raise ValueError('Authenticated panel bootstrap failed')
    data=value['data']
    if data['exercise']['state']!='DISARMED' or data['snapshot']['document']['events']:raise ValueError('Final exercise is not empty DISARMED')
    profiles={p['id']:p for p in data['profiles']}
    if profiles['first3h-all']['event_count']!=102 or profiles['first4h-all']['event_count']!=110:raise ValueError('Accepted templates changed')
    if not data['scoring']['fresh']:raise ValueError('Scoring export is stale')
    if api('/plugin/ccdc/api/status')[0]!=401:raise ValueError('Anonymous access unexpectedly allowed')
    if api('/plugin/ccdc/api/status',credentials['blue_api_key'])[0]!=403:raise ValueError('Blue access unexpectedly allowed')
    code,plugins=api('/api/v2/plugins',credentials['red_api_key'])
    if code!=200 or not any(p['name']=='ccdc' and p['enabled'] for p in plugins):raise ValueError('CCDC plugin is not enabled')
    directory=pathlib.Path('/run/summit-caldera-admin');sock=directory/'control.sock'
    if stat.S_IMODE(directory.stat().st_mode)!=0o750 or stat.S_IMODE(sock.stat().st_mode)!=0o660:raise ValueError('Socket permissions mismatch')
    if sock.stat().st_uid!=pwd.getpwnam('summit-coordinator').pw_uid or sock.stat().st_gid!=grp.getgrnam('summit-caldera').gr_gid:raise ValueError('Socket ownership mismatch')
    for port in (8888,8771,8772):
        with socket.create_connection(('127.0.0.1' if port==8888 else '10.77.70.20',port),timeout=3):pass
    for path in ('/etc/sudoers.d/90-summit-caldera-organizer',):
        if pathlib.Path(path).exists():raise ValueError('Temporary organizer sudo unexpectedly present')
    for unit in ('summit-caldera','summit-caldera-contact','summit-caldera-coordinator'):
        subprocess.run(['systemctl','is-active','--quiet',unit],check=True)
    print(json.dumps(dict(panel='PASS',native_plugin='ccdc',auth='red-only PASS',socket='PASS',templates={'first3h-all':102,'first4h-all':110},exercise='empty DISARMED',score_fresh=True,guest_listeners='8771/8772 PASS',temporary_sudo='absent',real_actions_requested=0)))

if __name__=='__main__':main()
