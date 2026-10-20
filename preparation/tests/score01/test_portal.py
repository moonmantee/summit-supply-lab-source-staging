import datetime as dt
from contextlib import closing
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

NOW = 1801713600  # deterministic UTC instant


def scoring_fixture(path, event=1, state='RUNNING'):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS competition_events(id INTEGER PRIMARY KEY,name TEXT,state TEXT,started_at TEXT);
        CREATE TABLE IF NOT EXISTS scorer_settings(id INTEGER PRIMARY KEY,current_event_id INTEGER);
        CREATE TABLE IF NOT EXISTS event_service_state(event_id INTEGER,service_id TEXT,consecutive_failures INTEGER,total_points INTEGER,total_sla_deductions INTEGER,last_status TEXT,last_timestamp TEXT);
        CREATE TABLE IF NOT EXISTS service_checks(id INTEGER PRIMARY KEY,event_id INTEGER,round_id INTEGER,timestamp TEXT,service_id TEXT,host_name TEXT,service_name TEXT,status TEXT,reason TEXT,latency_ms INTEGER,awarded_points INTEGER,sla_deduction INTEGER,consecutive_failures INTEGER);
        ''')
        db.execute('INSERT OR REPLACE INTO competition_events VALUES(?,?,?,?)', (event,f'Competition {event}',state,dt.datetime.fromtimestamp(NOW-60,dt.timezone.utc).isoformat()))
        db.execute('INSERT OR REPLACE INTO scorer_settings VALUES(1,?)',(event,))


class StoreTests(unittest.TestCase):
    def setUp(self):
        import portal_store
        self.module = portal_store
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scoring = self.root/'scoring.db'
        scoring_fixture(self.scoring)
        self.store = portal_store.PortalStore(self.root/'portal.db', self.scoring)

    def draft(self, **extra):
        return self.store.create({'code':'I01','title':'DNS request','hosts':'dc01','description':'Private future requirement','acceptance':'Exact A record','points':10, **extra}, now=NOW)

    def test_drafts_and_future_scheduled_cards_are_private(self):
        card=self.draft(release_at=NOW+100,deadline=NOW+500)
        self.assertEqual(self.store.snapshot(now=NOW)['injects'],[])
        self.assertEqual(self.store.snapshot(now=NOW,admin=True)['injects'][0]['id'],card)
        self.assertEqual(self.store.snapshot(now=NOW+101)['injects'][0]['status'],'Released')

    def test_stopped_event_does_not_release_scheduled_cards(self):
        self.draft(release_at=NOW+10,deadline=NOW+100)
        scoring_fixture(self.scoring,state='STOPPED')
        self.assertEqual(self.store.snapshot(now=NOW+20)['injects'],[])

    def test_missed_scheduled_window_is_visible_as_expired(self):
        self.draft(release_at=NOW+10,deadline=NOW+20)
        cards=self.store.snapshot(now=NOW+30)['injects']
        self.assertEqual(len(cards),1)
        self.assertEqual(cards[0]['status'],'Expired')

    def test_ready_timestamp_is_preserved_on_repeated_submission(self):
        card=self.draft(deadline=NOW+100)
        self.store.release(card,now=NOW)
        self.store.team_action(card,'ready',now=NOW+1)
        self.store.team_action(card,'ready',now=NOW+2)
        self.assertEqual(self.store.snapshot(now=NOW+3)['injects'][0]['ready_at'],NOW+1)

    def test_release_acknowledge_ready_and_permanent_award(self):
        card=self.draft(deadline=NOW+500)
        self.store.release(card,now=NOW)
        self.store.team_action(card,'acknowledge',now=NOW+1)
        self.assertEqual(self.store.snapshot(now=NOW+2)['injects'][0]['status'],'In progress')
        self.store.team_action(card,'ready',now=NOW+3)
        self.store.grade(card,True,'Verified DNS',now=NOW+4)
        snap=self.store.snapshot(now=NOW+1000)
        self.assertEqual(snap['injects'][0]['status'],'Completed')
        self.assertEqual(snap['scores']['inject_points'],10)
        with self.assertRaises(ValueError): self.store.grade(card,False,'revoke',now=NOW+1001)

    def test_deadline_blocks_late_team_submission_but_allows_review_of_ontime(self):
        card=self.draft(deadline=NOW+50)
        self.store.release(card,now=NOW)
        self.store.team_action(card,'ready',now=NOW+1)
        self.store.grade(card,True,'Reviewed on-time submission',now=NOW+60)
        late=self.store.create({'code':'I02','title':'Late','hosts':'forum01','description':'Task','acceptance':'Check','points':10,'deadline':NOW+50},now=NOW)
        self.store.release(late,now=NOW)
        with self.assertRaises(ValueError): self.store.team_action(late,'ready',now=NOW+51)
        with self.assertRaises(ValueError): self.store.grade(late,True,'late',now=NOW+51)

    def test_reset_isolates_event_and_scoring_database_is_unchanged(self):
        card=self.draft()
        self.store.release(card,now=NOW)
        self.store.grade(card,True,'Checked',now=NOW)
        before=hashlib.sha256(self.scoring.read_bytes()).hexdigest()
        self.store.snapshot(now=NOW)
        self.assertEqual(hashlib.sha256(self.scoring.read_bytes()).hexdigest(),before)
        scoring_fixture(self.scoring,event=2)
        snap=self.store.snapshot(now=NOW)
        self.assertEqual(snap['injects'],[])
        self.assertEqual(snap['scores']['inject_points'],0)
        with self.assertRaises(ValueError): self.store.release(card,now=NOW)

    def test_event_end_does_not_carry_into_a_new_event(self):
        self.store.settings({'event_end':'2026-10-04T20:00:00-06:00','team_name':'Blue Team'})
        scoring_fixture(self.scoring,event=2)
        settings=self.store.snapshot(now=NOW)['settings']
        self.assertNotIn('event_end',settings)
        self.assertEqual(settings['team_name'],'Blue Team')

    def test_two_simultaneous_grades_cannot_revoke_an_award(self):
        card=self.draft();self.store.release(card,now=NOW)
        barrier=threading.Barrier(2);results=[]
        def grade(passed):
            barrier.wait()
            try: self.store.grade(card,passed,'Concurrent check',now=NOW);results.append(passed)
            except ValueError: pass
        threads=[threading.Thread(target=grade,args=(p,)) for p in [True,False]]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(self.store.snapshot(now=NOW)['scores']['inject_points'],10)

    def test_service_projection_is_sanitized_and_staleness_is_explicit(self):
        old=dt.datetime.fromtimestamp(NOW-1000,dt.timezone.utc).isoformat()
        with closing(sqlite3.connect(self.scoring)) as db, db:
            db.execute('INSERT INTO service_checks VALUES(1,1,1,?,?,?,?,?,?,?,?,?,?)',(old,'shop-web','shop01','HTTPS','DOWN','secret internal reason',11,0,15,0))
            db.execute('INSERT INTO event_service_state VALUES(1,?,?,?,?,?,?)',('shop-web',0,20,15,'DOWN',old))
        snap=self.store.snapshot(now=NOW)
        self.assertTrue(snap['scorer']['stale'])
        self.assertEqual(snap['scores']['availability_net'],5)
        self.assertNotIn('secret internal reason',json.dumps(snap))

    def test_missing_scorer_cannot_create_or_release_injects(self):
        self.scoring.unlink()
        self.assertFalse(self.store.snapshot(now=NOW)['scorer']['available'])
        with self.assertRaises(ValueError): self.draft()

    def test_invalid_card_and_empty_grading_note_rejected(self):
        with self.assertRaises(ValueError): self.draft(points=-1)
        with self.assertRaises(ValueError): self.draft(deadline=NOW-1)
        card=self.draft()
        self.store.release(card,now=NOW)
        with self.assertRaises(ValueError): self.store.grade(card,True,'',now=NOW)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        import portal_server, portal_store
        self.module=portal_server
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.score=self.root/'scoring.db'; scoring_fixture(self.score)
        self.store=portal_store.PortalStore(self.root/'portal.db',self.score)
        self.auth=self.root/'auth.json'
        portal_server.write_auth(self.auth,'team-password-long','admin-password-long')
        self.files=self.root/'files'; self.files.mkdir()
        (self.files/'README.md').write_text('# Safe README')
        (self.files/'README.docx').write_bytes(b'PK fixture')
        self.server=portal_server.make_server(self.store,self.auth,self.files,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.port=self.server.server_address[1]

    def request(self,path,method='GET',body=None,cookie=None,csrf=None,host=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers={'Host':host or f'127.0.0.1:{self.port}'}
        if method=='POST': headers.update({'Content-Type':'application/json','Origin':'http://'+headers['Host']})
        if cookie: headers['Cookie']=cookie
        if csrf: headers['X-Portal-CSRF']=csrf
        if path in {'/portal/api/admin','/portal/api/inject'} and isinstance(body,dict):
            body={'event_id':1,**body}
        conn.request(method,path,json.dumps(body) if body is not None else None,headers)
        response=conn.getresponse(); data=response.read(); hs=dict(response.getheaders()); status=response.status; conn.close()
        return status,hs,data

    def login(self,role='team',host=None):
        s,h,b=self.request('/portal/api/login','POST',{'username':role,'password':role+'-password-long'},host=host)
        self.assertEqual(s,200,b)
        return h['Set-Cookie'].split(';')[0],json.loads(b)['csrf']

    def test_login_and_protected_readme_with_logout(self):
        self.assertEqual(self.request('/portal/api/state')[0],401)
        cookie,csrf=self.login()
        self.assertEqual(self.request('/portal/files/README.docx',cookie=cookie)[0],200)
        self.assertEqual(self.request('/portal/api/logout','POST',{},cookie,csrf)[0],200)
        self.assertEqual(self.request('/portal/api/state',cookie=cookie)[0],401)

    def test_team_cannot_read_drafts_or_use_admin_routes(self):
        self.store.create({'code':'I99','title':'hidden-secret','hosts':'dc01','description':'secret','acceptance':'private','points':1},now=NOW)
        cookie,csrf=self.login()
        s,_,b=self.request('/portal/api/state',cookie=cookie)
        self.assertEqual(s,200)
        self.assertNotIn(b'hidden-secret',b)
        self.assertEqual(self.request('/portal/api/admin','POST',{'action':'announce','message':'unauthorized'},cookie,csrf)[0],403)

    def test_csrf_and_origin_and_path_traversal_blocked(self):
        cookie,csrf=self.login()
        self.assertEqual(self.request('/portal/api/logout','POST',{},cookie)[0],403)
        self.assertEqual(self.request('/portal/files/../auth.json',cookie=cookie)[0],404)
        self.assertEqual(self.request('/portal/files/%2e%2e/auth.json',cookie=cookie)[0],404)
        self.assertEqual(self.request('/portal/api/state',cookie=cookie,host='evil.test')[0],403)

    def test_organizer_login_forbidden_through_team_endpoint(self):
        s,_,_=self.request('/portal/api/login','POST',{'username':'admin','password':'admin-password-long'},host='10.77.70.10:8080')
        self.assertEqual(s,403)
        cookie,csrf=self.login('admin')
        self.assertEqual(self.request('/portal/api/admin','POST',{'action':'announce','message':'Maintenance at 2 PM'},cookie,csrf)[0],200)

    def test_no_static_directory_exposes_source_or_database(self):
        cookie,_=self.login()
        for path in ['/portal/auth.json','/portal/portal.db','/portal/portal_server.py','/portal/api/control','/portal/files']:
            self.assertIn(self.request(path,cookie=cookie)[0],[404,405])

    def test_session_expiry_and_password_rotation_invalidate_access(self):
        cookie,_=self.login()
        with self.store.db() as db: db.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.request('/portal/api/state',cookie=cookie)[0],401)
        cookie,_=self.login()
        self.module.write_auth(self.auth,'new-team-password-long','new-admin-password-long')
        self.assertEqual(self.request('/portal/api/state',cookie=cookie)[0],401)

    def test_draft_attachment_requires_release_and_team_cannot_change_it(self):
        import base64
        card=self.store.create({'code':'I01','title':'Task','hosts':'dc01','description':'Task','acceptance':'Check','points':10})
        admin,csrf=self.login('admin')
        status,_,_=self.request('/portal/api/admin','POST',{'action':'attach','id':card,'name':'fixture.csv','content':base64.b64encode(b'fixture content').decode()},admin,csrf)
        self.assertEqual(status,200)
        team,_=self.login()
        self.assertEqual(self.request('/portal/attachments/1',cookie=team)[0],404)
        self.assertEqual(self.request('/portal/attachments/1',cookie=admin)[0],200)
        self.store.release(card)
        self.assertEqual(self.request('/portal/attachments/1',cookie=team)[2],b'fixture content')

    def test_five_failed_logins_are_rate_limited(self):
        for _ in range(5):
            status,_,_=self.request('/portal/api/login','POST',{'username':'team','password':'wrong-password'})
            self.assertEqual(status,401)
        self.assertEqual(self.request('/portal/api/login','POST',{'username':'team','password':'team-password-long'})[0],429)

    def test_stale_organizer_form_cannot_publish_into_new_event(self):
        cookie,csrf=self.login('admin')
        scoring_fixture(self.score,event=2)
        status,_,_=self.request('/portal/api/admin','POST',{'action':'announce','message':'Old event message','event_id':1},cookie,csrf)
        self.assertEqual(status,409)
        self.assertEqual(self.store.snapshot()['announcements'],[])

    def test_reset_between_api_guard_and_store_write_is_rejected(self):
        from unittest.mock import patch
        cookie,csrf=self.login('admin')
        previous=self.store.event()
        scoring_fixture(self.score,event=2)
        current=self.store.event()
        def observed(now=None,expected_event_id=None):
            if expected_event_id is None: return previous
            if expected_event_id!=current['id']:
                from portal_store import EventChanged
                raise EventChanged('The event changed.')
            return current
        with patch.object(self.store,'event',side_effect=observed):
            status,_,_=self.request('/portal/api/admin','POST',{'action':'announce','message':'Race test','event_id':1},cookie,csrf)
        self.assertEqual(status,409)
        self.assertEqual(self.store.snapshot()['announcements'],[])

    def test_rejected_request_body_closes_connection(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request('POST','/portal/api/login',body=b'junk',headers={'Content-Type':'text/plain','Host':f'127.0.0.1:{self.port}','Origin':f'http://127.0.0.1:{self.port}'})
        response=conn.getresponse(); response.read()
        self.assertEqual(response.status,400)
        # The backend closes the socket after its response; no unread body remains.
        if conn.sock is not None: self.assertEqual(conn.sock.recv(1),b'')
        conn.close()

    def test_invalid_content_length_closes_connection(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        conn.request('POST','/portal/api/login',body=b'junk',headers={'Content-Length':'invalid','Content-Type':'application/json','Host':f'127.0.0.1:{self.port}','Origin':f'http://127.0.0.1:{self.port}'})
        response=conn.getresponse();response.read()
        self.assertEqual(response.status,400)
        if conn.sock is not None:self.assertEqual(conn.sock.recv(1),b'')
        conn.close()


if __name__=='__main__': unittest.main()
