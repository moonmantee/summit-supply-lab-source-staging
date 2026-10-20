"""Visible fixed-action SYSTEM task. No arbitrary executor or automatic restart."""
import base64
import hashlib
import json
import os
import pathlib
import socket
import sys
import time
import traceback
from fixture_contract import authorization_transport,parse_command,strict_json
from pilot_agent import poll,answer_instruction
from windows_services import Services
from windows_notice import popup
from windows_worker import Worker

ROOT=pathlib.Path(r'C:\ProgramData\SummitCaldera')
PUBLIC=pathlib.Path(r'C:\ProgramData\SummitCalderaNotice')

def integrity():
    proof=strict_json((ROOT/'integrity.json').read_bytes())
    return all(pathlib.Path(path).is_file() and hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==digest for path,digest in proof.items())

def main():
    if os.name!='nt' or socket.gethostname().lower()!='mail01':raise ValueError('Wrong guest')
    if not integrity():raise ValueError('Installation changed; organizer inspection required')
    config=strict_json((ROOT/'config.json').read_bytes());native=Services(ROOT/'state')
    transport=authorization_transport(config['authorization'])
    def healthy():return integrity() and native.healthy()
    def apply(event):
        if not integrity():raise ValueError('Installation changed')
        if event['action']=='notice':
            result=popup(event['expires'])
            # Fixed visible evidence, readable by contestants, with no credentials.
            with (PUBLIC/'events.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'exercise':event['exercise'],'id':event['id'],'time':time.time(),'text':'RED TEAM WAS HERE',**result})+'\n');f.flush();os.fsync(f.fileno())
            return result
        return native.apply(event)
    worker=Worker(ROOT/'state/journal.sqlite3',transport,apply,healthy)
    def handler(item):
        if item.get('executor')!='summit-pilot' or item.get('payloads') or item.get('uploads') or item.get('deadman'):return answer_instruction(item)
        try:
            command=base64.b64decode(item['command'],validate=True).decode()
            if not command.startswith('summit-fixture '):return answer_instruction(item)
            result=worker.execute(*parse_command(command));status=0 if result.get('outcome')=='APPLIED' and result.get('acknowledged') is True else 1
        except Exception:result={'outcome':'REJECTED','acknowledged':False};status=1
        return {'id':item['id'],'pid':os.getpid(),'status':status,'exit_code':str(status),'output':base64.b64encode(json.dumps(result).encode()).decode(),'stderr':''}
    poll(config['contact'],None,instruction_handler=handler,before_poll=worker.heartbeat)

if __name__=='__main__':
    log=ROOT/'state/contact.log'
    with log.open('w' if log.exists() and log.stat().st_size>1048576 else 'a',encoding='utf-8',buffering=1) as stream:
        sys.stdout=sys.stderr=stream
        try:main()
        except Exception:
            traceback.print_exc();raise SystemExit(1)
