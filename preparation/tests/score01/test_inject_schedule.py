from contextlib import closing
import sqlite3
import unittest
from test_portal import StoreTests,NOW,scoring_fixture
import inject_services

class ScheduleTests(StoreTests):
    def task(self,code='I01'):
        return self.draft(code=code,service={'probe':'dns_record','host':'10.77.40.10','name':'orders.corp.summit.test','answer':'10.77.30.10'})

    def test_releases_from_next_start_and_waits_for_grace(self):
        self.task(); self.task('I02')
        scoring_fixture(self.scoring,state='STOPPED')
        self.store.arm_schedule(['I01','I02'],spacing=1800,grace=1800,duration=14400,now=NOW)
        self.assertEqual(self.store.snapshot(now=NOW+100)['injects'],[])
        scoring_fixture(self.scoring)
        with closing(sqlite3.connect(self.scoring)) as db,db:
            import datetime as dt
            db.execute('UPDATE competition_events SET started_at=? WHERE id=1',(dt.datetime.fromtimestamp(NOW+100,dt.timezone.utc).isoformat(),))
        import datetime as dt
        start=NOW+100
        state=self.store.snapshot(now=start)
        self.assertEqual([c['code'] for c in state['injects']],['I01'])
        self.assertEqual(state['injects'][0]['status'],'Grace period')
        self.assertEqual(inject_services.active_services(self.store.path,1,now=start+1799),[])
        self.assertEqual(len(inject_services.active_services(self.store.path,1,now=start+1800)),1)
        self.assertEqual(len(self.store.snapshot(now=start+1800)['injects']),2)
        self.assertEqual(len(inject_services.active_services(self.store.path,1,now=start+1800)),1)

    def test_manual_release_grace_and_released_schedule_is_immutable(self):
        card=self.task(); self.store.set_timing(card,release_offset=0,grace=120,now=NOW)
        self.store.release(card,now=NOW)
        self.assertEqual(inject_services.active_services(self.store.path,1,now=NOW+119),[])
        self.assertEqual(len(inject_services.active_services(self.store.path,1,now=NOW+120)),1)
        with self.assertRaises(ValueError): self.store.set_timing(card,release_offset=1,grace=5,now=NOW)

    def test_same_second_arm_and_start_releases_first_card(self):
        import datetime as dt
        self.task(); scoring_fixture(self.scoring,state='STOPPED')
        self.store.arm_schedule(['I01'],spacing=1800,grace=1800,duration=14400,now=NOW+.6)
        scoring_fixture(self.scoring)
        with closing(sqlite3.connect(self.scoring)) as db,db:
            db.execute('UPDATE competition_events SET started_at=? WHERE id=1',(dt.datetime.fromtimestamp(NOW,dt.timezone.utc).isoformat(timespec='seconds'),))
        snapshot=self.store.snapshot(now=NOW+.9)
        self.assertEqual(len(snapshot['injects']),1)
        self.assertEqual(snapshot['injects'][0]['status'],'Grace period')

    def test_reset_bootstraps_fresh_template_without_awards_and_keeps_grace(self):
        card=self.task()
        scoring_fixture(self.scoring,state='STOPPED')
        self.store.arm_schedule(['I01'],spacing=1800,grace=1800,duration=14400,now=NOW)
        self.store.enable_event_template(1,now=NOW)
        scoring_fixture(self.scoring,event=2)
        import datetime as dt
        with closing(sqlite3.connect(self.scoring)) as db,db:
            db.execute('UPDATE competition_events SET started_at=? WHERE id=2',(dt.datetime.fromtimestamp(NOW+10,dt.timezone.utc).isoformat(),))
        snapshot=self.store.snapshot(now=NOW+30)
        self.assertEqual([c['code'] for c in snapshot['injects']],['I01'])
        self.assertNotEqual(snapshot['injects'][0]['id'],card)
        self.assertEqual(snapshot['injects'][0]['earned_points'],0)
        self.assertEqual(snapshot['injects'][0]['released_at'],NOW+30)
        self.assertEqual(snapshot['injects'][0]['scoring_starts_at'],NOW+1830)
        self.assertEqual(inject_services.active_services(self.store.path,2,now=NOW+1829),[])
        self.assertEqual(len(inject_services.active_services(self.store.path,2,now=NOW+1830)),1)
        self.assertNotIn('inject_template',snapshot['settings'])

if __name__=='__main__': unittest.main()
