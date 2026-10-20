"""Event-scoped portal state and a read-only projection of the existing scorer."""
from contextlib import contextmanager
import datetime as dt
import json
from pathlib import Path
import re
import sqlite3
import time


class EventChanged(ValueError):
    pass


class PortalStore:
    def __init__(self, path, scoring_path, config_path=None):
        self.path, self.scoring_path = Path(path), Path(scoring_path)
        self.config_path = Path(config_path) if config_path else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS injects(
                id INTEGER PRIMARY KEY,event_id INTEGER NOT NULL,code TEXT NOT NULL,title TEXT NOT NULL,
                hosts TEXT NOT NULL,description TEXT NOT NULL,acceptance TEXT NOT NULL,points INTEGER NOT NULL,
                release_at REAL,deadline REAL,released_at REAL,ack_at REAL,ready_at REAL,
                completed_at REAL,earned_points INTEGER NOT NULL DEFAULT 0,feedback TEXT NOT NULL DEFAULT '',
                UNIQUE(event_id,code));
            CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY,event_id INTEGER,message TEXT,created_at REAL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event_id INTEGER,actor TEXT,action TEXT,detail TEXT,created_at REAL);
            CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY,inject_id INTEGER,name TEXT,stored_name TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS event_settings(event_id INTEGER,key TEXT,value TEXT,PRIMARY KEY(event_id,key));
            CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,role TEXT,csrf TEXT,expires REAL,auth_version TEXT);
            CREATE TABLE IF NOT EXISTS login_limits(client TEXT PRIMARY KEY,failures INTEGER,until REAL);
            ''')
            columns={r[1] for r in db.execute('PRAGMA table_info(injects)')}
            for name,kind in [('service_json','TEXT'),('auto_streak','INTEGER NOT NULL DEFAULT 0'),('auto_status','TEXT'),('release_offset','INTEGER'),('grace_seconds','INTEGER NOT NULL DEFAULT 0')]:
                if name not in columns: db.execute(f'ALTER TABLE injects ADD COLUMN {name} {kind}')
            self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path,timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                yield db
        finally: db.close()

    def scoring(self, now=None):
        now=time.time() if now is None else now
        try:
            db=sqlite3.connect(self.scoring_path.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
            db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                resumed='e.last_resumed_at' if 'last_resumed_at' in {r[1] for r in db.execute('PRAGMA table_info(competition_events)')} else 'e.started_at'
                event=db.execute('SELECT e.id,e.name,e.state,e.started_at,'+resumed+' AS last_resumed_at FROM competition_events e JOIN scorer_settings s ON s.current_event_id=e.id WHERE s.id=1').fetchone()
                if event is None: raise ValueError('No current event')
                services=[dict(r) for r in db.execute('SELECT service_id,consecutive_failures,total_points,total_sla_deductions,last_status,last_timestamp FROM event_service_state WHERE event_id=?',(event['id'],))]
                checks=[dict(r) for r in db.execute('SELECT timestamp,service_id,host_name,service_name,status,latency_ms,awarded_points,sla_deduction FROM service_checks WHERE event_id=? ORDER BY id DESC LIMIT 240',(event['id'],))]
            finally: db.close()
            configs=[]
            if self.config_path and self.config_path.exists():
                import scorer
                configs=scorer.resolve_services(scorer._load_config(self.config_path))
            from inject_services import active_services
            configs+=active_services(self.path,event['id'],now=now)
            known={s['service_id']:s for s in services}
            for item in configs:
                s=known.setdefault(item['id'],dict(service_id=item['id'],last_status=None,last_timestamp=None,total_points=0,total_sla_deductions=0,consecutive_failures=0))
                s.update(host_name=item['host_name'],service_name=item['service_name'],points=item['points'],sla_penalty=item['sla_penalty'])
            for check in checks:
                s=known.setdefault(check['service_id'],dict(service_id=check['service_id'],last_status=check['status'],last_timestamp=check['timestamp'],total_points=0,total_sla_deductions=0,consecutive_failures=0))
                s.setdefault('host_name',check['host_name']); s.setdefault('service_name',check['service_name'])
            timestamps=[s['last_timestamp'] for s in known.values() if s.get('last_timestamp')]
            latest=max(timestamps) if timestamps else None
            age=now-dt.datetime.fromisoformat(latest.replace('Z','+00:00')).timestamp() if latest else None
            return dict(available=True,event=dict(event),services=list(known.values()),checks=checks,last_update=latest,stale=event['state']=='RUNNING' and (age is None or age>360))
        except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
            return dict(available=False,event=None,services=[],checks=[],last_update=None,stale=True)

    def event(self, now=None, expected_event_id=None):
        s=self.scoring(now)
        if not s['available'] or s['event']['state']=='ARCHIVED': raise ValueError('Current scorer event is unavailable. Ask White Team to restore scoring access.')
        if expected_event_id is not None and s['event']['id']!=expected_event_id:
            raise EventChanged('The event changed. Refresh and review the new event before submitting.')
        return s['event']

    @staticmethod
    def log(db,event,actor,action,detail,now):
        db.execute('INSERT INTO audit(event_id,actor,action,detail,created_at) VALUES(?,?,?,?,?)',(event,actor,action,detail,now))

    def create(self,card,now=None,expected_event_id=None):
        now=time.time() if now is None else now
        event=self.event(now,expected_event_id)
        if not isinstance(card,dict): raise ValueError('An inject card must be a JSON object.')
        required={'code','title','hosts','description','acceptance','points'}
        if not required.issubset(card): raise ValueError('Code, title, systems, task, acceptance, and points are required.')
        for key,limit in [('code',20),('title',160),('hosts',160),('description',12000),('acceptance',8000)]:
            if not isinstance(card[key],str) or not card[key].strip() or len(card[key])>limit: raise ValueError('Invalid '+key)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,20}',card['code']): raise ValueError('Use letters, numbers, underscores or hyphens for the inject ID.')
        if isinstance(card['points'],bool) or not isinstance(card['points'],int) or not 0<=card['points']<=1000: raise ValueError('Points must be an integer from 0 to 1000.')
        release,deadline=card.get('release_at'),card.get('deadline')
        for value in [release,deadline]:
            if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not now<=value<=now+366*86400): raise ValueError('Times must be within the coming year.')
        if deadline is not None and release is not None and deadline<=release: raise ValueError('Deadline must follow release.')
        service=card.get('service')
        if service is not None:
            from inject_services import validate
            service=validate(service)
        with self.db() as db:
            try:
                cur=db.execute('INSERT INTO injects(event_id,code,title,hosts,description,acceptance,points,release_at,deadline) VALUES(?,?,?,?,?,?,?,?,?)',(event['id'],card['code'],card['title'].strip(),card['hosts'].strip(),card['description'].strip(),card['acceptance'].strip(),card['points'],release,deadline))
            except sqlite3.IntegrityError as error: raise ValueError('That inject ID already exists in this event.') from error
            if service is not None or card.get('automatic'): db.execute('UPDATE injects SET service_json=? WHERE id=?',(json.dumps(service or {}),cur.lastrowid))
            self.log(db,event['id'],'admin','create',card['code'],now)
            return cur.lastrowid

    def _card(self,db,ident,event):
        row=db.execute('SELECT * FROM injects WHERE id=? AND event_id=?',(ident,event['id'])).fetchone()
        if row is None: raise ValueError('Inject not found in this event.')
        return dict(row)

    def _release_due(self,event,now):
        self._ensure_event_template(event,now)
        if event['state']!='RUNNING': return
        with self.db() as db:
            settings=dict(db.execute('SELECT key,value FROM event_settings WHERE event_id=?',(event['id'],)))
            if settings.get('schedule_armed_at') and not settings.get('schedule_anchor'):
                # Anchor to the next lifecycle Start/Resume, including existing stopped events.
                actual=self.event(now,expected_event_id=event['id'])
                stamp=actual.get('last_resumed_at') or actual.get('started_at')
                anchor=dt.datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp() if stamp else now
                if anchor<float(settings['schedule_armed_at']): return
                duration=int(settings['schedule_duration'])
                db.execute('INSERT OR REPLACE INTO event_settings VALUES(?,?,?)',(event['id'],'schedule_anchor',str(anchor)))
                db.execute('INSERT OR REPLACE INTO event_settings VALUES(?,?,?)',(event['id'],'event_end',dt.datetime.fromtimestamp(anchor+duration,dt.timezone.utc).isoformat()))
                db.execute('UPDATE injects SET release_at=?+release_offset,deadline=? WHERE event_id=? AND released_at IS NULL AND release_offset IS NOT NULL',(anchor,anchor+duration,event['id']))
            due=db.execute("SELECT id,code,release_at FROM injects WHERE event_id=? AND released_at IS NULL AND release_at IS NOT NULL AND release_at<=? AND (service_json IS NULL OR service_json<>'{}')",(event['id'],now)).fetchall()
            for row in due:
                db.execute('UPDATE injects SET released_at=? WHERE id=? AND released_at IS NULL',(max(row['release_at'],now) if db.execute('SELECT grace_seconds FROM injects WHERE id=?',(row['id'],)).fetchone()[0] else row['release_at'],row['id']))
                self.log(db,event['id'],'scheduler','release',row['code'],now)

    def release(self,ident,now=None,expected_event_id=None):
        now=time.time() if now is None else now; event=self.event(now,expected_event_id)
        with self.db() as db:
            card=self._card(db,ident,event)
            if card['released_at'] is not None: raise ValueError('Inject already released.')
            if card['service_json'] is not None:
                from inject_services import validate
                validate(json.loads(card['service_json']))
            if card['deadline'] is not None and card['deadline']<=now: raise ValueError('Deadline has already passed.')
            db.execute('UPDATE injects SET released_at=? WHERE id=?',(now,ident))
            self.log(db,event['id'],'admin','release',card['code'],now)

    def team_action(self,ident,action,now=None,expected_event_id=None):
        if action not in {'acknowledge','ready'}: raise ValueError('Unknown team action.')
        now=time.time() if now is None else now; event=self.event(now,expected_event_id)
        if event['state']!='RUNNING': raise ValueError('Team actions are available while the event is running.')
        self._release_due(event,now)
        with self.db() as db:
            card=self._card(db,ident,event)
            if card['released_at'] is None: raise ValueError('Inject is not released.')
            if card['completed_at'] is not None: raise ValueError('Inject is already completed.')
            if card['deadline'] is not None and now>=card['deadline']: raise ValueError('The deadline has passed.')
            column='ack_at' if action=='acknowledge' else 'ready_at'
            db.execute(f'UPDATE injects SET {column}=COALESCE({column},?) WHERE id=?',(now,ident))
            self.log(db,event['id'],'team',action,card['code'],now)

    def grade(self,ident,passed,note,now=None,expected_event_id=None):
        now=time.time() if now is None else now; event=self.event(now,expected_event_id)
        if not isinstance(passed,bool) or not isinstance(note,str) or not note.strip() or len(note)>2000: raise ValueError('A grading result and feedback are required.')
        with self.db() as db:
            card=self._card(db,ident,event)
            if card['service_json'] is not None: raise ValueError('Automatic injects are graded by recorded service checks.')
            if card['released_at'] is None: raise ValueError('Release the inject before grading.')
            if card['completed_at'] is not None: raise ValueError('Earned points are permanent; this inject is already completed.')
            if passed and card['deadline'] is not None and now>=card['deadline'] and (card['ready_at'] is None or card['ready_at']>=card['deadline']): raise ValueError('No on-time submission exists for this expired inject.')
            db.execute('UPDATE injects SET feedback=?,completed_at=?,earned_points=?,ready_at=? WHERE id=?',(note.strip(),now if passed else None,card['points'] if passed else 0,card['ready_at'] if passed else None,ident))
            self.log(db,event['id'],'admin','grade',json.dumps({'code':card['code'],'passed':passed,'feedback':note.strip()}),now)

    def announce(self,message,now=None,expected_event_id=None):
        now=time.time() if now is None else now; event=self.event(now,expected_event_id)
        if not isinstance(message,str) or not message.strip() or len(message)>2000: raise ValueError('Announcement must contain 1–2000 characters.')
        with self.db() as db:
            db.execute('INSERT INTO announcements(event_id,message,created_at) VALUES(?,?,?)',(event['id'],message.strip(),now))
            self.log(db,event['id'],'admin','announce',message.strip(),now)

    @staticmethod
    def status(card,now):
        if card['completed_at'] is not None: return 'Completed'
        if card['released_at'] is None: return 'Scheduled' if card['release_at'] is not None or card.get('release_offset') is not None else 'Draft'
        if now<card['released_at']+card.get('grace_seconds',0): return 'Grace period'
        if card['ready_at'] is not None: return 'Awaiting verification'
        if card['deadline'] is not None and now>=card['deadline']: return 'Expired'
        return 'In progress' if card['ack_at'] is not None else 'Released'

    def snapshot(self,now=None,admin=False):
        now=time.time() if now is None else now; scoring=self.scoring(now)
        event=scoring['event']; injects=[]; announcements=[]; audit=[]; archive=[]
        if event:
            self._release_due(event,now)
            self.sync_services(event,now)
            with self.db() as db:
                condition='' if admin else ' AND released_at IS NOT NULL'
                injects=[dict(r) for r in db.execute('SELECT * FROM injects WHERE event_id=?'+condition+' ORDER BY code',(event['id'],))]
                for card in injects:
                    card['scoring_starts_at']=card['released_at']+card['grace_seconds'] if card['released_at'] is not None else None
                    raw=card.pop('service_json')
                    card['automatic']=raw is not None
                    card['needs_configuration']=raw=='{}'
                    if raw and raw!='{}':
                        from inject_services import PROFILES
                        service=json.loads(raw)
                        card['service_id']='inject-'+str(card['id'])
                        card['service_summary']=dict(probe=service['probe'],name=PROFILES[service['probe']],host=service['host'],points=service['points'],sla_penalty=service['sla_penalty'])
                    card['status']=self.status(card,now)
                    card['attachments']=[dict(r) for r in db.execute('SELECT id,name FROM attachments WHERE inject_id=?',(card['id'],))]
                announcements=[dict(r) for r in db.execute('SELECT id,message,created_at FROM announcements WHERE event_id=? ORDER BY id DESC LIMIT 30',(event['id'],))]
                if admin:
                    audit=[dict(r) for r in db.execute('SELECT actor,action,detail,created_at FROM audit WHERE event_id=? ORDER BY id DESC LIMIT 100',(event['id'],))]
                    archive=[dict(r) for r in db.execute('SELECT event_id,COUNT(*) AS inject_count,SUM(earned_points) AS earned_points FROM injects WHERE event_id<>? GROUP BY event_id ORDER BY event_id DESC',(event['id'],))]
        with self.db() as db:
            settings=dict(db.execute("SELECT key,value FROM settings WHERE key IN ('team_name','help_contact','credential_contact','console_url')"))
            if event: settings.update(dict(db.execute('SELECT key,value FROM event_settings WHERE event_id=?',(event['id'],))))
        # Unreleased draft point values must not disclose future tasks to the team.
        points=sum(s['total_points'] for s in scoring['services']); sla=sum(s['total_sla_deductions'] for s in scoring['services'])
        return dict(server_time=now,event=event,scorer={k:scoring[k] for k in ['available','stale','last_update']},services=scoring['services'],history=scoring['checks'],injects=injects,announcements=announcements,audit=audit,archive=archive,settings=settings,scores=dict(availability_points=points,sla_deductions=sla,availability_net=points-sla,inject_points=sum(c['earned_points'] for c in injects),total=points-sla+sum(c['earned_points'] for c in injects)))

    def configure_service(self,ident,service,expected_event_id=None):
        from inject_services import validate
        service=validate(service); event=self.event(expected_event_id=expected_event_id)
        with self.db() as db:
            card=self._card(db,ident,event)
            if card['released_at'] is not None: raise ValueError('Service settings are immutable after release. Create a new task for changed requirements.')
            db.execute('UPDATE injects SET service_json=? WHERE id=?',(json.dumps(service),ident))
            self.log(db,event['id'],'admin','configure-service',card['code'],time.time())

    def set_timing(self,ident,release_offset,grace,now=None,expected_event_id=None):
        now=time.time() if now is None else now
        event=self.event(now,expected_event_id)
        for value in [release_offset,grace]:
            if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=86400: raise ValueError('Timing must be whole seconds from 0 to 86400.')
        with self.db() as db:
            card=self._card(db,ident,event)
            if card['released_at'] is not None: raise ValueError('Released task timing is immutable.')
            db.execute('UPDATE injects SET release_offset=?,grace_seconds=? WHERE id=?',(release_offset,grace,ident))
            self.log(db,event['id'],'admin','timing',card['code'],now)

    def enable_event_template(self,source_event_id,now=None):
        now=time.time() if now is None else now
        with self.db() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM injects WHERE event_id=? ORDER BY code',(source_event_id,))]
            if not rows or any(row['release_offset'] is None for row in rows): raise ValueError('Template requires scheduled task cards.')
            duration=db.execute("SELECT value FROM event_settings WHERE event_id=? AND key='schedule_duration'",(source_event_id,)).fetchone()
            if duration is None: raise ValueError('Template requires an event duration.')
            keys=['code','title','hosts','description','acceptance','points','service_json','release_offset','grace_seconds']
            cards=[]
            for row in rows:
                card={key:row[key] for key in keys}
                card['attachments']=[dict(r) for r in db.execute('SELECT name,stored_name FROM attachments WHERE inject_id=?',(row['id'],))]
                cards.append(card)
            template={'duration':int(duration[0]),'cards':cards}
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('inject_template',json.dumps(template)))
            self.log(db,source_event_id,'admin','enable-event-template','Fresh tasks and schedule on future events',now)

    def _ensure_event_template(self,event,now):
        if event['state'] not in {'READY','STOPPED','RUNNING'}: return
        with self.db() as db:
            template=db.execute("SELECT value FROM settings WHERE key='inject_template'").fetchone()
            if not template or db.execute('SELECT 1 FROM injects WHERE event_id=?',(event['id'],)).fetchone(): return
            template=json.loads(template[0])
            actual=self.event(now,expected_event_id=event['id'])
            anchor=None
            if actual['state']=='RUNNING':
                stamp=actual.get('last_resumed_at') or actual.get('started_at')
                anchor=dt.datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp() if stamp else now
            for card in template['cards']:
                keys=['code','title','hosts','description','acceptance','points','service_json','release_offset','grace_seconds']
                ident=db.execute('INSERT INTO injects(event_id,'+','.join(keys)+') VALUES('+','.join(['?']*10)+')',(event['id'],*[card[k] for k in keys])).lastrowid
                # Resources are immutable files; create fresh event-scoped references only.
                for attachment in card.get('attachments',[]):
                    db.execute('INSERT INTO attachments(inject_id,name,stored_name) VALUES(?,?,?)',(ident,attachment['name'],attachment['stored_name']))
            values={'schedule_armed_at':str(int(now)),'schedule_duration':str(template['duration']),'schedule_anchor':str(anchor) if anchor is not None else ''}
            if anchor is not None:
                db.execute('UPDATE injects SET release_at=?+release_offset,deadline=? WHERE event_id=?',(anchor,anchor+template['duration'],event['id']))
                values['event_end']=dt.datetime.fromtimestamp(anchor+template['duration'],dt.timezone.utc).isoformat()
            for key,value in values.items(): db.execute('INSERT OR REPLACE INTO event_settings VALUES(?,?,?)',(event['id'],key,value))
            self.log(db,event['id'],'scheduler','initialize-event','Fresh default injects and schedule; no prior awards copied',now)

    def arm_schedule(self,codes,spacing,grace,duration,now=None,expected_event_id=None):
        now=time.time() if now is None else now
        event=self.event(now,expected_event_id)
        if event['state'] not in {'READY','STOPPED'}: raise ValueError('Arm a schedule before starting the event.')
        if not isinstance(codes,list) or not codes or len(set(codes))!=len(codes): raise ValueError('Select unique task codes.')
        for value in [spacing,grace,duration]:
            if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=86400: raise ValueError('Schedule values must be whole seconds within one day.')
        if duration<=spacing*(len(codes)-1)+grace+360: raise ValueError('Allow time for three check rounds after the final grace period.')
        with self.db() as db:
            cards=[db.execute('SELECT id,released_at FROM injects WHERE event_id=? AND code=?',(event['id'],code)).fetchone() for code in codes]
            if any(c is None or c['released_at'] is not None for c in cards): raise ValueError('All scheduled cards must be unreleased in the current event.')
            for index,card in enumerate(cards): db.execute('UPDATE injects SET release_offset=?,grace_seconds=?,release_at=NULL,deadline=NULL WHERE id=?',(index*spacing,grace,card['id']))
            # Lifecycle Start timestamps are whole seconds; use matching precision.
            for key,value in {'schedule_armed_at':str(int(now)),'schedule_anchor':'','schedule_duration':str(duration),'event_end':''}.items(): db.execute('INSERT OR REPLACE INTO event_settings VALUES(?,?,?)',(event['id'],key,value))
            self.log(db,event['id'],'admin','arm-schedule',json.dumps({'codes':codes,'spacing':spacing,'grace':grace,'duration':duration}),now)

    def sync_services(self,event,now):
        from contextlib import closing
        with self.db() as db:
            cards=[dict(r) for r in db.execute('SELECT * FROM injects WHERE event_id=? AND released_at IS NOT NULL AND service_json IS NOT NULL',(event['id'],))]
        with closing(sqlite3.connect(self.scoring_path.resolve().as_uri()+'?mode=ro',uri=True)) as score:
            current=score.execute('SELECT current_event_id FROM scorer_settings WHERE id=1').fetchone()
            if not current or current[0]!=event['id']: return
            for card in cards:
                rows=score.execute('SELECT timestamp,status FROM service_checks WHERE event_id=? AND service_id=? ORDER BY id',(event['id'],'inject-'+str(card['id']))).fetchall()
                streak=0; completed=None; status=None
                for stamp,status in rows:
                    when=dt.datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()
                    if when<card['released_at']+card['grace_seconds'] or when>now: continue
                    streak=streak+1 if status=='PASS' else 0
                    if streak>=3 and completed is None and (card['deadline'] is None or when<card['deadline']): completed=when
                with self.db() as db:
                    db.execute('UPDATE injects SET auto_streak=?,auto_status=? WHERE id=?',(min(streak,3),status,card['id']))
                    if completed is not None:
                        cur=db.execute("UPDATE injects SET completed_at=?,earned_points=points,feedback='Automatically verified by three consecutive passing service rounds.' WHERE id=? AND completed_at IS NULL",(completed,card['id']))
                        if cur.rowcount: self.log(db,event['id'],'scorer','auto-grade',card['code'],completed)

    def settings(self,values,expected_event_id=None):
        if not isinstance(values,dict): raise ValueError('Event settings must be a JSON object.')
        event=self.event(expected_event_id=expected_event_id) if expected_event_id is not None or 'event_end' in values else None
        allowed={'team_name','help_contact','credential_contact','console_url','event_end'}
        if set(values)-allowed: raise ValueError('Unknown event setting.')
        for key,value in values.items():
            if not isinstance(value,str) or len(value)>300: raise ValueError('Invalid setting value.')
            if key=='console_url' and value and not re.match(r'^https?://[^\s]+$',value): raise ValueError('Console link must be an HTTP or HTTPS URL.')
            if key=='event_end' and value:
                try: dt.datetime.fromisoformat(value.replace('Z','+00:00'))
                except ValueError: raise ValueError('Invalid event end time.')
        with self.db() as db:
            for key,value in values.items():
                if key=='event_end':
                    db.execute('INSERT OR REPLACE INTO event_settings VALUES(?,?,?)',(event['id'],key,value.strip()))
                else: db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,value.strip()))
