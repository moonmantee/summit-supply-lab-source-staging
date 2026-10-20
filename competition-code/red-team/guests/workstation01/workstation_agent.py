"""Visible root contact, fixed notices only. No business-service mutation API."""
import base64,hashlib,json,os,pathlib,socket,subprocess,sys,time
APP=pathlib.Path('/opt/summit-caldera-workstation')
sys.path.insert(0,str(APP))
from fixture_contract import authorization_transport,parse_command,strict_json
from pilot_agent import poll,answer_instruction
from workstation_worker import Worker
from workstation_notice import popup,desktop_session,PUBLIC
STATE=pathlib.Path('/var/lib/summit-caldera-workstation')
CONFIG=pathlib.Path('/etc/summit-caldera-workstation/config.json')
SERVICES=('sshd','firewalld','sssd','summit-aeacus','gdm')
def snapshot():
    return {'services':{n:subprocess.run(['/usr/bin/systemctl','is-active',n],check=True,capture_output=True,text=True,timeout=3).stdout.strip() for n in SERVICES},
      'selinux':subprocess.run(['/usr/sbin/getenforce'],check=True,capture_output=True,text=True,timeout=3).stdout.strip()}
def integrity():
    proof=strict_json((STATE/'integrity.json').read_bytes())
    return all(pathlib.Path(p).is_file() and hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==digest for p,digest in proof.items())
def healthy():
    try:return integrity() and snapshot()==strict_json((STATE/'baseline.json').read_bytes()) and bool(desktop_session())
    except Exception:return False
def main():
    if os.geteuid()!=0 or socket.gethostname()!='workstation01.corp.summit.test':raise ValueError('Wrong native identity')
    if not healthy():raise ValueError('Native baseline/session/integrity changed')
    config=strict_json(CONFIG.read_bytes());transport=authorization_transport(config['authorization'])
    def apply(event):
        if not healthy():raise ValueError('Native baseline/session/integrity changed')
        result=popup(event['expires'])
        with (PUBLIC/'events.jsonl').open('a') as f:
            f.write(json.dumps({'exercise':event['exercise'],'id':event['id'],'time':time.time(),'text':'RED TEAM WAS HERE',**result})+'\n');f.flush();os.fsync(f.fileno())
        return result
    worker=Worker(STATE/'journal.sqlite3',transport,apply,healthy)
    def handler(item):
        if item.get('executor')!='summit-pilot' or item.get('payloads') or item.get('uploads') or item.get('deadman'):return answer_instruction(item)
        try:
            command=base64.b64decode(item['command'],validate=True).decode()
            if not command.startswith('summit-fixture '):return answer_instruction(item)
            result=worker.execute(*parse_command(command));status=0 if result.get('outcome')=='APPLIED' and result.get('acknowledged') is True else 1
        except Exception:result={'outcome':'REJECTED','acknowledged':False};status=1
        return {'id':item['id'],'pid':os.getpid(),'status':status,'exit_code':str(status),'output':base64.b64encode(json.dumps(result).encode()).decode(),'stderr':''}
    poll(config['contact'],None,instruction_handler=handler,before_poll=worker.heartbeat)
if __name__=='__main__':main()
