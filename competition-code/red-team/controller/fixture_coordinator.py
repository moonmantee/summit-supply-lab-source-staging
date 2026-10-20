"""DISARMED-by-default competition coordinator and exact mTLS event authorization."""
import argparse
import hashlib
import json
import pathlib
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'legacy'))
from scheduler import Engine
from state import Store
from manifest import validate_scenario
from fixture_contract import identifiers,strict_json,NoRedirect
from contact_gateway import Gateway,Handler

class Core:
    def __init__(self,engine,scoring,queue,guests,clock=time.time):
        self.engine,self.scoring,self.queue,self.guests,self.clock=engine,scoring,queue,guests,clock
        self.lock=threading.RLock();self.health_reports={}
        with engine.store.transaction() as c:
            c.execute('CREATE TABLE IF NOT EXISTS caldera_links(exercise TEXT,event TEXT,state TEXT,link TEXT,created REAL,busy_until REAL,PRIMARY KEY(exercise,event))')
    def score(self):
        try:return self.scoring()
        except Exception:return None
    def health(self,guest,healthy):
        if guest not in self.guests or type(healthy) is not bool: raise ValueError('Invalid health report')
        with self.lock:self.health_reports[guest]=(self.clock(),healthy)
    def healthy(self,guest):
        reported,healthy=self.health_reports.get(guest,(-100,False))
        return healthy and 0<=self.clock()-reported<=10
    def tick(self):
        with self.lock:
            scoring=self.score();self.engine.heartbeat(scoring)
            with self.engine.store.transaction() as c:
                c.execute("UPDATE dispatch SET outcome='EXPIRED' WHERE outcome='DISPATCHED' AND expires<=?",(self.clock(),))
                rows=c.execute("SELECT id FROM exercises WHERE state='RUNNING'").fetchall()
                # Reserve one global disruption through worst-case acceptance/recovery margin.
                busy=c.execute("SELECT 1 FROM caldera_links l JOIN dispatch d ON l.exercise=d.exercise AND l.event=d.event WHERE d.outcome='ACCEPTED' OR (d.outcome IN ('DISPATCHED','APPLIED','FAILED') AND l.busy_until>?)",(self.clock(),)).fetchone()
                prior_faults=c.execute("SELECT d.guest,l.busy_until FROM caldera_links l JOIN dispatch d ON l.exercise=d.exercise AND l.event=d.event WHERE l.busy_until>0 AND d.outcome IN ('APPLIED','FAILED')").fetchall()
            if busy:return
            for row in rows:
                for guest in self.guests:
                    if not self.healthy(guest):continue
                    if any(fault['guest']==guest and self.health_reports[guest][0]<fault['busy_until']-5 for fault in prior_faults):continue
                    event=self.engine.next_event(row['id'],guest,scoring)
                    if not event:continue
                    with self.engine.store.transaction() as c:
                        busy_until=event['expires']+event['duration']+5 if 'duration' in event else 0
                        c.execute('INSERT INTO caldera_links VALUES(?,?,?,?,?,?)',(event['exercise'],event['id'],'ISSUING',None,self.clock(),busy_until))
                    try:
                        link=self.queue(event)
                        if not isinstance(link,str) or not link:raise ValueError('Invalid CALDERA link response')
                        state='ISSUED'
                    except Exception:
                        state,link='UNCERTAIN',None
                    with self.engine.store.transaction() as c:
                        c.execute('UPDATE caldera_links SET state=?,link=? WHERE exercise=? AND event=?',(state,link,event['exercise'],event['id']))
                    return
    def fetch(self,guest,exercise,event):
        identifiers(exercise,event)
        with self.lock:
            scoring=self.score();self.engine.heartbeat(scoring)
            with self.engine.store.transaction() as c:
                row=c.execute('SELECT d.*,e.state,e.scoring_event_id,l.state AS link_state FROM dispatch d JOIN exercises e ON d.exercise=e.id JOIN caldera_links l ON d.exercise=l.exercise AND d.event=l.event WHERE d.exercise=? AND d.event=? AND d.guest=?',(exercise,event,guest)).fetchone()
            if (row is None or row['state']!='RUNNING' or row['outcome']!='DISPATCHED'
                or row['link_state']!='ISSUED' or not self.clock()<row['expires']<=self.clock()+15
                or scoring!={'id':row['scoring_event_id'],'state':'RUNNING'} or not self.healthy(guest)):
                raise ValueError('Event is not currently authorized')
            matches=[item for item in self.engine.scenario if item['guest']==guest and item['id']==event]
            if len(matches)!=1:raise ValueError('Unknown event')
            action=matches[0]
            result={'exercise':exercise,'id':event,'guest':guest,'action':action['action'],
                    'target':action['target'],'expires':row['expires']}
            if 'duration' in action:result['duration']=action['duration']
            return result
    def accept(self,guest,exercise,event):
        with self.lock:
            self.fetch(guest,exercise,event)
            self.engine.store.accept(exercise,event,guest,self.score(),self.clock())
    def ack(self,guest,exercise,event,outcome):
        identifiers(exercise,event)
        with self.lock:self.engine.store.ack(exercise,event,guest,outcome)

class Caldera:
    def __init__(self,config):
        self.key=config['api_key'];self.guests=config['guests']
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def api(self,path,body=None):
        request=urllib.request.Request('http://127.0.0.1:8888'+path,
            None if body is None else json.dumps(body).encode(),headers={'KEY':self.key,'Content-Type':'application/json'})
        with self.opener.open(request,timeout=4) as response:
            data=response.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise ValueError('Oversize backend response')
            return json.loads(data)
    def queue(self,event):
        exercise,eventid=identifiers(event['exercise'],event['id'])
        paw=self.guests[event['guest']]['paw']
        host=self.guests[event['guest']].get('host',event['guest'])
        platform=self.guests[event['guest']].get('platform','linux')
        if platform not in ('linux','windows'):raise ValueError('Unsupported enrolled platform')
        agents=self.api('/api/v2/agents')
        matches=[a for a in agents if a['paw']==paw and a['host']==host
                 and a['group']=='summit-pilot' and a['executors']==['summit-pilot']
                 and a.get('platform')==platform]
        if len(matches)!=1:raise ValueError('Expected compatible connected agent')
        ability=str(uuid.uuid5(uuid.UUID('f6c9bf6f-60eb-4878-9bcb-07c8a22886ce'),exercise+':'+eventid))
        command='summit-fixture '+exercise+' '+eventid
        expected={'ability_id':ability,'name':'Summit fixture '+event['action'],'description':'Fixed fixture broker event; fresh authorization required',
                  'tactic':'impact','technique_id':'T1489','technique_name':'Service Stop','repeatable':False,
                  'executors':[{'name':'summit-pilot','platform':platform,'command':command,'timeout':15}]}
        try:
            found=self.api('/api/v2/abilities/'+ability)
            if (len(found['executors'])!=1 or found['executors'][0]['command']!=command
                    or found['executors'][0]['name']!='summit-pilot'
                    or found['executors'][0]['platform']!=platform):raise ValueError('Changed event ability preserved')
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
            self.api('/api/v2/abilities',expected)
        links=self.api('/api/rest',{'index':'task','paw':paw,'ability_id':ability,'obfuscator':'plain-text'})
        if len(links)!=1:raise ValueError('Expected single fixture link')
        return links[0]['id']

class AuthorizationHandler(Handler):
    def do_POST(self):
        route=self.requestline.split(' ')[1]
        if route not in ('/event','/accept','/ack','/status'):return self.reply(404)
        fingerprint=hashlib.sha256(self.connection.getpeercert(binary_form=True)).hexdigest()
        matches=[(name,item) for name,item in self.server.config['enrollments'].items()
                 if item['cert_sha256']==fingerprint and item['source']==self.client_address[0]]
        if len(matches)!=1:return self.reply(403)
        guest=matches[0][0]
        lengths=self.headers.get_all('Content-Length',[])
        if self.headers.get('Transfer-Encoding') or len(lengths)!=1 or not lengths[0].isdigit():return self.reply(400)
        size=int(lengths[0])
        if not 0<size<=512:return self.reply(413)
        try:
            data=strict_json(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('Invalid body')
            if route=='/status':
                if set(data)!={'healthy'}:raise ValueError('Invalid health fields')
                self.server.core.health(guest,data['healthy']);result={'ok':True}
            else:
                fields={'exercise','id'}|({'outcome'} if route=='/ack' else set())
                if set(data)!=fields:raise ValueError('Unexpected authorization fields')
                identifiers(data['exercise'],data['id'])
                if route=='/event':result={'event':self.server.core.fetch(guest,data['exercise'],data['id'])}
                elif route=='/accept':self.server.core.accept(guest,data['exercise'],data['id']);result={'ok':True}
                else:self.server.core.ack(guest,data['exercise'],data['id'],data['outcome']);result={'ok':True}
            return self.reply(200,json.dumps(result).encode())
        except Exception:return self.reply(409,b'{"ok":false}')

class AuthorizationServer(Gateway):
    def __init__(self,config,core):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(config['certificate'],config['key'])
        context.load_verify_locations(config['ca']);context.verify_mode=ssl.CERT_REQUIRED
        super().__init__((config['bind'],config['port']),config,context)
        self.RequestHandlerClass=AuthorizationHandler;self.core=core
    def service_actions(self):
        try:self.core.tick()
        except Exception:
            # A monitor error revokes future dispatch; never print secrets or replay.
            with self.core.lock:self.core.engine.recover_restart()

def scoring(path):
    value=strict_json(pathlib.Path(path).read_bytes())
    if set(value)!={'id','state','generated'} or not 0<=time.time()-value['generated']<=4:
        raise ValueError('Scoring export stale')
    return {'id':value['id'],'state':value['state']}

def restore_snapshot(store,config):
    from panel_store import PanelStore
    panel_store=PanelStore(store)
    panel_store.initialize(None,{})
    with store.transaction() as c:
        current=c.execute('SELECT id FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
    snapshot=panel_store.read_snapshot(current['id']) if current else None
    if snapshot is not None:return panel_store,snapshot['document']['events']
    # Only an initial legacy migration needs the old recovery/import record.
    scenario=validate_scenario(strict_json(pathlib.Path(config['scenario']).read_bytes()),
                              {g:v['targets'] for g,v in config['guests'].items()})
    panel_store.initialize(scenario,{})
    return panel_store,scenario

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('command',choices=('serve','status','start','pause','stop'))
    args=parser.parse_args()
    if args.command=='status':
        from panel_client import AdminClient
        print(json.dumps(AdminClient().call({'op':'status','args':{}})));return
    if args.command!='serve':raise ValueError('Use fixture_control.py for lifecycle changes')
    config=strict_json(pathlib.Path(args.config).read_bytes())
    store=Store(config['state']);panel_store,scenario=restore_snapshot(store,config)
    engine=Engine(store,scenario)
    with store.transaction() as c:
        current=c.execute('SELECT * FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
    if args.command=='serve':
        from panel_store import PanelStore
        from panel_service import PanelService
        from panel_socket import AdminServer
        import pwd
        engine.recover_restart()
        core=Core(engine,lambda:scoring(config['scoring_export']),Caldera(config).queue,
                  {g:v['paw'] for g,v in config['guests'].items()})
        def score_details():
            value=strict_json(pathlib.Path(config['scoring_export']).read_bytes())
            return {'age':max(0,time.time()-value['generated'])}
        service=PanelService(core,panel_store,guests=config['guests'],score_details=score_details)
        admin=AdminServer('/run/summit-caldera-admin/control.sock',service,
                          {0,pwd.getpwnam('summit-caldera').pw_uid})
        admin.start()
        try:
            with AuthorizationServer(config,core) as server:server.serve_forever(poll_interval=0.25)
        finally:admin.close()

if __name__=='__main__':main()
