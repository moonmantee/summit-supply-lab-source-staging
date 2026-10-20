"""Fresh-authorized, durably deduplicated worker for the fixed scored Apache target."""
import contextlib
import os
import pathlib
import sqlite3
import time
from first_three_hours import validate_event

class Worker:
    def __init__(self,config,transport,journal,executor=None,clock=time.time):
        self.config,self.transport,self.clock=config,transport,clock;self.journal=pathlib.Path(journal)
        if executor is None:
            from apache_backend import Apache,private_state
            from business_actions import Actions,STATE
            private_state();executor=Actions(STATE/'recovery.sqlite3',Apache()).apply
        self.executor=executor
        with contextlib.closing(sqlite3.connect(self.journal)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS seen(exercise TEXT,event TEXT,outcome TEXT,PRIMARY KEY(exercise,event))');db.commit()
        if os.name=='posix':self.journal.chmod(0o600)
    def poll_once(self):
        try:event=self.transport('/poll',{'guest':self.config['guest'],'token':''})['event']
        except Exception:return {'outcome':'UNREACHABLE'}
        try:
            validate_event(event,self.clock())
            if self.config['guest']!='shop01' or self.config['targets'].get('apache')!='apache2.service':raise ValueError('Unapproved installation target')
        except Exception:return {'outcome':'REJECTED'}
        with contextlib.closing(sqlite3.connect(self.journal)) as db:
            try:
                db.execute('INSERT INTO seen VALUES(?,?,?)',(event['exercise'],event['id'],'ACCEPTED'));db.commit()
            except sqlite3.IntegrityError:return {'outcome':'DUPLICATE'}
            identity={'guest':'shop01','token':'','exercise':event['exercise'],'id':event['id']}
            try:allowed=self.transport('/accept',identity).get('ok') is True
            except Exception:allowed=False
            try:
                if not allowed:outcome='REJECTED'
                else:
                    validate_event(event,self.clock());outcome=self.executor(event)['outcome']
                    if outcome not in ('APPLIED','FAILED','REJECTED'):raise ValueError('Invalid adapter outcome')
            except Exception:outcome='FAILED'
            db.execute('UPDATE seen SET outcome=? WHERE exercise=? AND event=?',(outcome,event['exercise'],event['id']));db.commit()
        try:ack=self.transport('/ack',{**identity,'outcome':outcome}).get('ok') is True
        except Exception:ack=False
        return {'outcome':outcome,'acknowledged':ack}
