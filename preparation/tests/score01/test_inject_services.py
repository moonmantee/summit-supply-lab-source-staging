from contextlib import closing
import datetime as dt
import json
import sqlite3
import unittest
from unittest.mock import patch,Mock
import tempfile
from pathlib import Path
import time
from test_portal import StoreTests, NOW


class AutomaticTests(StoreTests):
    def configured(self, **extra):
        return self.draft(service={'probe':'ftp_share','host':'10.77.30.20','username':'inventory_reader','password':'private-test-secret','file':'inventory.csv','sha256':'a'*64,'points':2,'sla_penalty':7}, **extra)

    def check(self, timestamp, status='PASS', event=1):
        with closing(sqlite3.connect(self.scoring)) as db, db:
            db.execute('INSERT INTO service_checks(event_id,round_id,timestamp,service_id,host_name,service_name,status,latency_ms,awarded_points,sla_deduction) VALUES(?,?,?,?,?,?,?,?,?,?)', (event,timestamp,dt.datetime.fromtimestamp(timestamp,dt.timezone.utc).isoformat(),'inject-1','forum01','Inventory FTP',status,1,2,0))

    def test_activation_secret_redaction_and_three_round_award(self):
        import inject_services
        card=self.configured(deadline=NOW+100)
        self.assertEqual(inject_services.active_services(self.store.path,1), [])
        self.store.release(card,now=NOW)
        self.assertEqual(inject_services.active_services(self.store.path,1,now=NOW)[0]['id'],'inject-1')
        self.check(NOW+1); self.check(NOW+2)
        snapshot=self.store.snapshot(now=NOW+3)
        self.assertNotIn('private-test-secret',json.dumps(snapshot))
        self.assertEqual(snapshot['injects'][0]['auto_streak'],2)
        self.assertEqual(snapshot['scores']['inject_points'],0)
        self.check(NOW+4)
        self.assertEqual(self.store.snapshot(now=NOW+5)['scores']['inject_points'],10)
        self.check(NOW+6,'DOWN')
        self.assertEqual(self.store.snapshot(now=NOW+7)['scores']['inject_points'],10)
        self.assertEqual(len(inject_services.active_services(self.store.path,1,now=NOW+7)),1)
        self.assertEqual(inject_services.active_services(self.store.path,2),[])

    def test_down_resets_streak_and_late_pass_does_not_award(self):
        card=self.configured(deadline=NOW+5); self.store.release(card,now=NOW)
        self.check(NOW+1); self.check(NOW+2,'DOWN'); self.check(NOW+3); self.check(NOW+4); self.check(NOW+6)
        self.assertEqual(self.store.snapshot(now=NOW+7)['scores']['inject_points'],0)

    def test_cannot_manually_award_automatic_or_target_infrastructure(self):
        card=self.configured(); self.store.release(card,now=NOW)
        with self.assertRaises(ValueError): self.store.grade(card,True,'override',now=NOW+1)
        with self.assertRaises(ValueError): self.draft(code='BAD',service={'probe':'https_upgrade','host':'10.77.70.10'})

    def test_three_passes_recorded_before_deadline_can_sync_after_stop(self):
        card=self.configured(deadline=NOW+5); self.store.release(card,now=NOW)
        for offset in [1,2,3]: self.check(NOW+offset)
        from test_portal import scoring_fixture
        scoring_fixture(self.scoring,state='STOPPED')
        self.assertEqual(self.store.snapshot(now=NOW+20)['scores']['inject_points'],10)

    def test_unconfigured_automatic_task_cannot_release_or_schedule(self):
        card=self.draft(automatic=True,release_at=NOW+1)
        with self.assertRaises(ValueError): self.store.release(card,now=NOW)
        snapshot=self.store.snapshot(now=NOW+2,admin=True)
        self.assertTrue(snapshot['injects'][0]['needs_configuration'])
        self.assertIsNone(snapshot['injects'][0]['released_at'])


class IntegrationTests(unittest.TestCase):
    def test_real_scorer_includes_new_service_and_readonly_existing_dashboard(self):
        import scorer, portal_store, portal_scoreboard
        from lifecycle import migrate_lifecycle, transition_event
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); database=root/'results.db'; portal=root/'portal.db'; config=root/'config.json'
            with closing(sqlite3.connect(database)) as db:
                scorer.initialize_schema(db); migrate_lifecycle(db,dt.datetime.now(dt.timezone.utc).isoformat()); transition_event(db,'start',dt.datetime.now(dt.timezone.utc).isoformat())
            config.write_text(json.dumps({'services':[{'id':'baseline','host_name':'forum01','service_name':'HTTP','probe':'banner','points':1,'sla_penalty':5}], 'portal_database':str(portal)}))
            store=portal_store.PortalStore(portal,database,config)
            ident=store.create({'code':'FTP','title':'FTP share','hosts':'forum01','description':'Publish fixture','acceptance':'Retrieve fixture','points':10,'service':{'probe':'ftp_share','host':'10.77.30.20','username':'reader','password':'SECRET','file':'inventory.csv','sha256':'a'*64}})
            store.release(ident)
            with patch.object(scorer,'run_probe',return_value=('PASS','Test transaction verified')):
                for _ in range(3): scorer.run_scoring_round(config,database,root/'public')
            self.assertEqual(store.snapshot()['scores']['inject_points'],10)
            html=portal_scoreboard.page(store).decode()
            self.assertIn('Inventory FTP',html)
            self.assertNotIn('control-panel',html); self.assertNotIn('summit-control-token',html); self.assertNotIn('SECRET',html)
            with closing(sqlite3.connect(database)) as db: transition_event(db,'stop',dt.datetime.now(dt.timezone.utc).isoformat())
            result=scorer.run_scoring_round(config,database,root/'public')
            self.assertFalse(result['recorded'])
            with closing(sqlite3.connect(database)) as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM scoring_rounds').fetchone()[0],3)

    def test_probe_failure_never_exposes_password(self):
        import inject_services
        with patch.dict(inject_services.PROBES,{'ftp_share':Mock(side_effect=OSError('secret-password-in-exception'))}):
            result=inject_services.run_probe({'probe':'ftp_share'})
        self.assertEqual(result[0],'DOWN'); self.assertNotIn('secret-password',result[1])


if __name__=='__main__': unittest.main()
