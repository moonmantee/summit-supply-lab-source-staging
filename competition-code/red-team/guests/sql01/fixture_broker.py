"""Privileged fixed-event Unix broker; no shell, command text or arbitrary target input."""
import argparse
import json
import os
import pathlib
import socket
import socketserver
import struct
import sys
import time
import urllib.request
from fixture_contract import identifiers,strict_json,authorization_transport

class Broker:
    def __init__(self,config,transport,worker_factory,health_probe):
        self.config,self.transport,self.worker_factory,self.health_probe=config,transport,worker_factory,health_probe
    def report(self):
        try:
            healthy=self.health_probe() is True
            reply=self.transport('/status',{'healthy':healthy})
            return healthy and reply.get('ok') is True
        except Exception:return False
    def execute(self,exercise,eventid):
        identifiers(exercise,eventid)
        if not self.report():return {'outcome':'REJECTED','acknowledged':False}
        event=self.transport('/event',{'exercise':exercise,'id':eventid}).get('event')
        if not isinstance(event,dict) or (event.get('exercise'),event.get('id'),event.get('guest'))!=(exercise,eventid,self.config['guest']):
            raise ValueError('Authorization event identity mismatch')
        def bounded_transport(route,payload):
            if route=='/poll':return {'event':event}
            if route not in ('/accept','/ack'):raise ValueError('Unsupported worker route')
            if (payload['exercise'],payload['id'],payload['guest'])!=(exercise,eventid,self.config['guest']):
                raise ValueError('Worker event identity mismatch')
            body={'exercise':exercise,'id':eventid}
            if route=='/ack':body['outcome']=payload['outcome']
            return self.transport(route,body)
        worker=self.worker_factory({'guest':self.config['guest'],'token':'',
            'targets':self.config['targets']},bounded_transport,self.config['journal'])
        try:return worker.poll_once()
        finally:self.report()

def probe_fixture():
    from service_actions import SystemdBackend,ServiceOutages,STATE
    backend=SystemdBackend();state=backend.inspect();backend.ensure_recovery_ready()
    if not state['active'] or state['enabled']!='enabled':return False
    if backend.config_state()!='NORMAL' or backend.executable_state()!='NORMAL' or backend.definition_state()!='NORMAL':return False
    outages=ServiceOutages(STATE/'recovery',backend)
    with outages.locked():
        paths=outages.paths()
        if len(paths)>1000:return False
        if any(outages.read(path)['phase']!='RESTORED' for path in paths):return False
    with urllib.request.urlopen('http://127.0.0.1:8780',timeout=2) as response:return response.status==200

class BrokerHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid not in (0,self.server.agent_uid):raise ValueError('Unapproved Unix caller')
            body=self.rfile.readline(513)
            if len(body)>512 or not body.endswith(b'\n'):raise ValueError('Invalid local framing')
            data=strict_json(body)
            if isinstance(data,dict) and data=={'status':True}:
                result={'healthy':self.server.broker.report()}
            elif isinstance(data,dict) and set(data)=={'exercise','id'}:
                result=self.server.broker.execute(*identifiers(data['exercise'],data['id']))
            else:raise ValueError('Unsupported local request')
        except Exception:result={'outcome':'REJECTED','acknowledged':False}
        self.wfile.write(json.dumps(result).encode()+b'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:raise ValueError('Root broker identity required')
    config=strict_json(pathlib.Path(args.config).read_bytes())
    sys.path.insert(0,'/opt/summit-red-agent')
    from agent import Worker
    def factory(worker_config,transport,journal):
        if config.get('business_enabled',False):
            event=transport('/poll',{'guest':config['guest'],'token':''})['event']
            if str(event.get('action','')).startswith('business_'):
                from business_worker import Worker as BusinessWorker
                return BusinessWorker(worker_config,transport,journal)
        return Worker(worker_config,transport,journal)
    def health():
        if not probe_fixture():return False
        if config.get('business_enabled',False):
            from apache_backend import Apache,private_state
            from business_actions import Actions,STATE
            private_state();return Actions(STATE/'recovery.sqlite3',Apache()).ready()
        return True
    broker=Broker(config,authorization_transport(config),factory,health)
    address=pathlib.Path('/run/summit-caldera-broker/broker.sock')
    if address.is_symlink():raise ValueError('Unexpected broker socket symlink')
    if address.exists():
        import stat
        info=address.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=0:raise ValueError('Changed local socket preserved')
        address.unlink()
    with socketserver.UnixStreamServer(str(address),BrokerHandler) as server:
        os.chown(address,0,config['agent_gid']);address.chmod(0o660)
        server.agent_uid=config['agent_uid'];server.broker=broker
        server.serve_forever(poll_interval=0.25)

if __name__=='__main__':main()
