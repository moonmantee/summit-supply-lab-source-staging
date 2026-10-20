import copy
import json
import pathlib
import sys
import tempfile
import unittest
import uuid
import threading
from test_panel_catalog import GUESTS
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload/controller'))
from legacy.state import Store
from legacy.scheduler import Engine
from fixture_coordinator import Core
from panel_store import PanelStore
try:
    from panel_service import PanelService
except ImportError: PanelService = None


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PanelService, 'panel service not implemented')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.now = 100.; self.score = {'id': 3, 'state': 'RUNNING'}
        self.store = Store(pathlib.Path(self.tmp.name) / 'state.db'); self.eid = self.store.create_exercise(3)
        self.engine = Engine(self.store, [], lambda: self.now)
        self.core = Core(self.engine, lambda: self.score, lambda e: self.fail('no live queue'), GUESTS, lambda: self.now)
        self.ps = PanelStore(self.store, lambda: self.now, lambda: 10**9)
        self.event = dict(id='event1', guest='shop01', action='notice', target='desktop', at=0, window=15)
        self.doc = dict(name='Custom', duration=10800, events=[self.event])
        self.ps.initialize([], {'test': self.doc, 'empty': dict(self.doc, events=[])})
        self.svc = PanelService(self.core, self.ps, lambda: self.now, guests=GUESTS)

    def status(self): return self.svc.handle({'op': 'status', 'args': {}}, 'test')['data']
    def request(self, op, args=None):
        s = self.status()
        return dict(op=op, args=args or {}, expected_exercise_id=s['exercise']['id'],
                    expected_lifecycle_revision=s['lifecycle_revision'], idempotency_key=uuid.uuid4().hex)
    def call(self, op, args=None): return self.svc.handle(self.request(op, args), 'test')
    def load(self, profile='test'):
        r = self.call('exercise.load', dict(profile_id=profile, revision=1)); self.assertTrue(r['ok'], r)

    def test_empty_start_and_score_gates(self):
        self.assertFalse(self.call('exercise.start')['ok'])
        self.load(); self.score = None
        self.assertFalse(self.call('exercise.start')['ok'])
        self.score = dict(id=4, state='RUNNING')
        self.assertFalse(self.call('exercise.start')['ok'])
        self.score = dict(id=3, state='RUNNING')
        self.assertTrue(self.call('exercise.start')['ok'])  # offline guests do not block exercise

    def test_hour4_pilot_loads_disarmed_and_dispatches_after_explicit_start(self):
        events = json.loads((ROOT / 'payload/controller/profiles/hour4-mail01-web-pilot.json').read_text())
        document = dict(name='Quick pilot', duration=14400, events=events)
        created = self.call('profiles.create', dict(document=document))
        self.assertTrue(created['ok'], created)
        profile = created['data']['id']
        self.load(profile)
        eid = self.status()['exercise']['id']
        self.core.health('mail01', True)
        self.assertEqual(self.status()['exercise']['state'], 'DISARMED')
        self.assertIsNone(self.engine.next_event(eid, 'mail01', self.score))
        self.assertTrue(self.call('exercise.start')['ok'])
        self.now += 2
        self.status()
        self.assertIsNone(self.engine.next_event(eid, 'mail01', self.score))
        self.now += 1
        self.status()
        dispatched = self.engine.next_event(eid, 'mail01', self.score)
        self.assertEqual(dispatched['id'], events[0]['id'])
        self.assertEqual(dispatched['action'], 'business_launch_fault')
        self.assertIsNone(self.engine.next_event(eid, 'mail01', self.score))

    def test_pause_freezes_elapsed_and_revokes(self):
        self.load(); self.call('exercise.start'); eid = self.status()['exercise']['id']
        self.now += 2
        with self.store.transaction() as tx: tx.execute('INSERT INTO dispatch VALUES(?,?,?,?,?)', (eid, 'event1', 'shop01', 'DISPATCHED', 115))
        self.assertTrue(self.call('exercise.pause')['ok'])
        self.now += 50
        self.assertEqual(self.status()['exercise']['elapsed'], 2)
        with self.store.transaction() as tx: self.assertEqual(tx.execute('SELECT outcome FROM dispatch').fetchone()[0], 'REVOKED')
        with self.assertRaises(ValueError): self.core.accept('shop01', eid, 'event1')

    def test_retry_and_changed_body(self):
        req = self.request('profiles.create', {'document': self.doc})
        first = self.svc.handle(req, 'test')
        self.assertTrue(first['ok']); self.assertEqual(first, self.svc.handle(req, 'test'))
        req['args']['document']['name'] = 'Changed'
        self.assertEqual(self.svc.handle(req, 'test')['error']['code'], 'conflict')

    def test_stale_tab_aba_and_ticks(self):
        self.load(); self.call('exercise.start'); self.call('exercise.pause')
        stale = self.request('exercise.resume')
        self.assertTrue(self.call('exercise.resume')['ok']); self.call('exercise.pause')
        self.assertEqual(self.svc.handle(stale, 'test')['error']['code'], 'conflict')
        self.call('exercise.resume'); before = self.status()['lifecycle_revision']; self.now += 1
        self.assertEqual(self.status()['lifecycle_revision'], before)

    def test_save_during_run_does_not_change_snapshot(self):
        self.load(); self.call('exercise.start')
        self.assertTrue(self.call('profiles.save', dict(profile_id='test', expected_profile_revision=1, document=dict(self.doc, events=[])))['ok'])
        self.assertEqual(len(self.engine.scenario), 1)
        self.assertFalse(self.call('exercise.load', dict(profile_id='test', revision=2))['ok'])
        self.call('exercise.pause')
        self.assertFalse(self.call('exercise.load', dict(profile_id='test', revision=2))['ok'])

    def test_restart_and_automatic_transitions_increment_revision(self):
        self.load(); self.call('exercise.start'); before = self.status()['lifecycle_revision']
        self.engine.recover_restart()
        self.assertEqual(self.status()['exercise']['state'], 'PAUSED')
        self.assertGreater(self.status()['lifecycle_revision'], before)
        self.call('exercise.resume'); before = self.status()['lifecycle_revision']; self.score = None
        self.assertEqual(self.status()['exercise']['state'], 'STOPPED')
        self.assertGreater(self.status()['lifecycle_revision'], before)

    def test_unknown_and_arbitrary_fields_rejected(self):
        for req in [{'op':'systemctl','args':{}}, {'op':'status','args':{'path':'/etc/passwd'}}, {'op':'status','args':{},'actor':'root'}]:
            self.assertFalse(self.svc.handle(req, 'test')['ok'])

    def test_duplicate_rejects_boolean_revision(self):
        self.assertFalse(self.call('profiles.duplicate',dict(profile_id='test',expected_profile_revision=True,name='Copy'))['ok'])

    def test_automatic_finish_and_scoring_pause(self):
        self.load(); self.call('exercise.start'); before = self.status()['lifecycle_revision']
        self.score = dict(id=3, state='PAUSED')
        self.assertEqual(self.status()['exercise']['state'], 'PAUSED')
        self.assertGreater(self.status()['lifecycle_revision'], before)
        self.score = dict(id=3, state='RUNNING'); self.call('exercise.resume')
        before = self.status()['lifecycle_revision']; self.now += 10801
        self.assertEqual(self.status()['exercise']['state'], 'FINISHED')
        self.assertGreater(self.status()['lifecycle_revision'], before)

    def test_pause_serializes_with_acceptance(self):
        self.load(); self.call('exercise.start'); eid = self.status()['exercise']['id']
        self.core.health('shop01', True)
        with self.store.transaction() as tx:
            tx.execute('INSERT INTO dispatch VALUES(?,?,?,?,?)', (eid, 'event1', 'shop01', 'DISPATCHED', 115))
            tx.execute('INSERT INTO caldera_links VALUES(?,?,?,?,?,?)', (eid, 'event1', 'ISSUED', 'fake-link', 100, 0))
        request = self.request('exercise.pause'); entered = threading.Event(); results = []
        def acceptance():
            entered.set()
            try: self.core.accept('shop01', eid, 'event1'); results.append('accepted')
            except ValueError: results.append('rejected')
        with self.core.lock:
            thread = threading.Thread(target=acceptance); thread.start(); entered.wait(1)
            self.assertTrue(self.svc.handle(request, 'test')['ok'])
        thread.join(2)
        self.assertEqual(results, ['rejected'])

    def test_no_catchup_after_pause_or_offline_window(self):
        self.load(); self.call('exercise.start'); self.now += 20
        self.core.health('shop01', True)
        self.assertIsNone(self.engine.next_event(self.status()['exercise']['id'], 'shop01', self.score))
        self.assertEqual(self.status()['outcomes'][0]['outcome'], 'EXPIRED')

    def test_idempotency_ttl_and_audit_bounds(self):
        with self.store.transaction() as tx:
            tx.executemany('INSERT INTO panel_idempotency VALUES(?,?,?,?)', [(str(i), 'old', '{}', 0) for i in range(10001)])
            tx.executemany('INSERT INTO panel_admin_audit(created,actor,op,exercise) VALUES(?,?,?,?)', [(0,'test','read',self.eid)]*10001)
        self.now = 86401
        self.assertTrue(self.call('profiles.create', dict(document=self.doc))['ok'])
        with self.store.transaction() as tx:
            self.assertEqual(tx.execute('SELECT count(*) FROM panel_idempotency').fetchone()[0], 1)
            self.assertEqual(tx.execute('SELECT count(*) FROM panel_admin_audit').fetchone()[0], 10000)

if __name__ == '__main__': unittest.main()
