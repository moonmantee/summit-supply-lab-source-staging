"""Fixed forum01 events, online acceptance and durable at-most-once execution."""
import contextlib
import math
import pathlib
import sqlite3
import time
from fixture_contract import identifiers

ACTIONS=frozenset(('business_stop','business_disable','business_restart_off'))

def validate_event(event,now):
    if isinstance(event,dict) and event.get('action') in ('business_binary_rename','business_launch_fault'):
        from four_hours import validate_event as fourth
        if event.get('guest')!='forum01':raise ValueError('Wrong native guest')
        return fourth(event,now)
    if not isinstance(event,dict):raise ValueError('Invalid event')
    notice=event.get('action')=='notice'
    fields={'exercise','id','guest','action','target','expires'}| (set() if notice else {'duration'})
    if set(event)!=fields:raise ValueError('Unexpected event fields')
    identifiers(event['exercise'],event['id'])
    if event['guest']!='forum01':raise ValueError('Wrong guest')
    if notice:
        if event['target']!='desktop':raise ValueError('Unsupported notice')
    elif (event['action'] not in ACTIONS or event['target'] not in ('web','ftp')
          or type(event['duration']) is not int or not 15<=event['duration']<=180):raise ValueError('Unsupported forum fault')
    if event.get('action')=='business_restart_off' and event['target']=='web':raise ValueError('Web has no restart actions to disable')
    if (type(event['expires']) not in (int,float) or not math.isfinite(event['expires'])
        or not now<event['expires']<=now+15):raise ValueError('Expired authorization')
    return event

class Worker:
    def __init__(self,path,transport,executor,healthy,clock=time.time):
        self.path=pathlib.Path(path);self.transport=transport;self.executor=executor;self.healthy=healthy;self.clock=clock
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE IF NOT EXISTS seen(exercise TEXT,event TEXT,action TEXT,outcome TEXT,created REAL,PRIMARY KEY(exercise,event))');db.commit()
    def observe(self):
        # Strictly passive. No deadline, recovery executor, service start or policy write.
        healthy=self.healthy()
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            if healthy:
                db.execute("UPDATE seen SET outcome='REPAIRED' WHERE action!='notice' AND outcome IN ('ACCEPTED','APPLIED','FAILED')");db.commit()
            unresolved=db.execute("SELECT 1 FROM seen WHERE action!='notice' AND outcome IN ('ACCEPTED','APPLIED','FAILED')").fetchone()
        return healthy and not unresolved
    def heartbeat(self):
        try:self.transport('/status',{'healthy':self.observe()})
        except Exception:pass
    def execute(self,exercise,eventid):
        identifiers(exercise,eventid);identity={'exercise':exercise,'id':eventid}
        try:
            event=self.transport('/event',identity)['event'];validate_event(event,self.clock())
            if event['exercise']!=exercise or event['id']!=eventid:raise ValueError('Wrong response identity')
            if not self.observe():raise ValueError('Guest has unrepaired fault or changed baseline')
        except Exception:return {'outcome':'REJECTED','acknowledged':False}
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            try:
                db.execute('INSERT INTO seen VALUES(?,?,?,?,?)',(exercise,eventid,event['action'],'ACCEPTED',self.clock()));db.commit()
            except sqlite3.IntegrityError:return {'outcome':'DUPLICATE','acknowledged':False}
            outcome='REJECTED'
            try:
                if self.transport('/accept',identity).get('ok') is True:
                    validate_event(event,self.clock())
                    outcome=self.executor(event)['outcome']
                    if outcome not in ('APPLIED','FAILED','REJECTED'):raise ValueError('Bad adapter outcome')
            except Exception:outcome='FAILED'
            db.execute('UPDATE seen SET outcome=? WHERE exercise=? AND event=?',(outcome,exercise,eventid));db.commit()
        try:ack=self.transport('/ack',{**identity,'outcome':outcome}).get('ok') is True
        except Exception:ack=False
        return {'outcome':outcome,'acknowledged':ack}
