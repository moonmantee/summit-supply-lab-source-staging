"""Fresh-authorized, durably deduplicated worker for the fixed scored Apache target."""
import contextlib
import os
import pathlib
import sqlite3
import time
from first_three_hours import validate_event,BUSINESS_TARGETS

class Worker:
    def __init__(self,config,transport,journal,executor=None,clock=time.time):
        self.config,self.transport,self.clock=config,transport,clock;self.journal=pathlib.Path(journal)
        if executor is None:
            if config['guest']=='sql01':from mariadb_backend import MariaDB as Backend,private_state
            elif config['guest']=='shop01':from apache_backend import Apache as Backend,private_state
            else:raise ValueError('Unapproved native guest')
            from business_actions import Actions,STATE
            private_state();actions=Actions(STATE/'recovery.sqlite3',Backend())
            def executor(event):
                if event['action']=='notice':
                    from sql_notice import apply_notice
                    return apply_notice(event['exercise'],event['id'],event['target'],config['targets'],event['expires'])
                return actions.apply(event)
        self.executor=executor
        with contextlib.closing(sqlite3.connect(self.journal)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS seen(exercise TEXT,event TEXT,outcome TEXT,PRIMARY KEY(exercise,event))');db.commit()
        if os.name=='posix':self.journal.chmod(0o600)
    def validate(self,event):
        if isinstance(event,dict) and event.get('action')=='notice' and self.config['guest']=='sql01':
            from sql_notice import valid
            if set(event)!={'exercise','id','guest','action','target','expires'} or event['guest']!='sql01' or event['target'] not in ('desktop','wall'):
                raise ValueError('Invalid SQL notice')
            valid(event['exercise'],event['id'],event['expires'],self.clock)
            if event['expires']>self.clock()+15:raise ValueError('Invalid notice expiry')
        else:validate_event(event,self.clock())
        guest=self.config['guest'];target,unit=BUSINESS_TARGETS[guest]
        if event['guest']!=guest or self.config['targets'].get(target)!=unit:raise ValueError('Unapproved installation target')
    def poll_once(self):
        try:event=self.transport('/poll',{'guest':self.config['guest'],'token':''})['event']
        except Exception:return {'outcome':'UNREACHABLE'}
        try:
            self.validate(event)
        except Exception:return {'outcome':'REJECTED'}
        with contextlib.closing(sqlite3.connect(self.journal)) as db:
            try:
                db.execute('INSERT INTO seen VALUES(?,?,?)',(event['exercise'],event['id'],'ACCEPTED'));db.commit()
            except sqlite3.IntegrityError:return {'outcome':'DUPLICATE'}
            identity={'guest':self.config['guest'],'token':'','exercise':event['exercise'],'id':event['id']}
            try:allowed=self.transport('/accept',identity).get('ok') is True
            except Exception:allowed=False
            try:
                if not allowed:outcome='REJECTED'
                else:
                    self.validate(event);outcome=self.executor(event)['outcome']
                    if outcome not in ('APPLIED','FAILED','REJECTED'):raise ValueError('Invalid adapter outcome')
            except Exception:outcome='FAILED'
            db.execute('UPDATE seen SET outcome=? WHERE exercise=? AND event=?',(outcome,event['exercise'],event['id']));db.commit()
        try:ack=self.transport('/ack',{**identity,'outcome':outcome}).get('ok') is True
        except Exception:ack=False
        return {'outcome':outcome,'acknowledged':ack}
