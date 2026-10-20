import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'legacy'))

class FixtureTests(unittest.TestCase):
    def test_broker_refuses_mismatched_event_or_failed_online_health(self):
        from fixture_broker import Broker
        worker=mock.Mock()
        config={'guest':'shop01','targets':{},'journal':'unused'}
        transport=mock.Mock(return_value={'ok':True})
        broker=Broker(config,transport,worker,lambda:False)
        self.assertEqual(broker.execute('exercise1','event1')['outcome'],'REJECTED')
        worker.assert_not_called()
        def wrong(route,body):
            if route=='/status':return {'ok':True}
            return {'event':{'exercise':'exercise1','id':'different','guest':'shop01'}}
        broker=Broker(config,wrong,worker,lambda:True)
        with self.assertRaises(ValueError):broker.execute('exercise1','event1')
        worker.assert_not_called()

    def test_fixture_agent_cannot_send_command_text_to_broker(self):
        import base64
        import fixture_agent
        for text in ('summit-fixture a b;id','summit-fixture a ../b','sh -c id'):
            instruction={'id':'link1','executor':'summit-pilot','command':base64.b64encode(text.encode()).decode()}
            with mock.patch.object(fixture_agent,'local_request') as request:
                self.assertEqual(fixture_agent.answer_fixture(instruction)['status'],1)
                request.assert_not_called()

    def test_command_accepts_identifiers_only(self):
        from fixture_contract import parse_command
        self.assertEqual(parse_command('summit-fixture exercise1 event1'),('exercise1','event1'))
        for text in ('sh -c id','summit-fixture a b;id','summit-fixture a ../x',
                     'summit-fixture a b extra','summit-fixture a\nb','summit-fixture a '+'b'*65):
            with self.assertRaises(ValueError): parse_command(text)

    def make_core(self,path,queue=None):
        from fixture_coordinator import Core
        from scheduler import Engine
        from state import Store
        self.now=100.0; self.scoring={'id':3,'state':'RUNNING'}
        self.events=[]
        scenario=[{'id':'event1','guest':'shop01','action':'service_stop','target':'demo',
                   'at':0,'window':8,'duration':5}]
        store=Store(path); self.eid=store.create_exercise(3)
        engine=Engine(store,scenario,clock=lambda:self.now,wall_clock=lambda:self.now)
        core=Core(engine,lambda:self.scoring,queue or (lambda event:self.events.append(event) or 'link1'),
                  {'shop01':'summit-shop01'},clock=lambda:self.now)
        return core

    def test_no_dispatch_without_fresh_broker_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db')
            core.engine.transition(self.eid,'start'); core.tick()
            self.assertEqual(self.events,[])
            core.health('shop01',True); self.now+=11; core.tick()
            self.assertEqual(self.events,[])

    def test_pause_event_switch_expiry_and_replay_refuse_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db')
            core.engine.transition(self.eid,'start'); core.health('shop01',True); core.tick()
            self.assertEqual(len(self.events),1)
            self.assertEqual(core.fetch('shop01',self.eid,'event1')['duration'],5)
            self.scoring={'id':4,'state':'RUNNING'}
            with self.assertRaises(ValueError):core.accept('shop01',self.eid,'event1')
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db')
            core.engine.transition(self.eid,'start'); core.health('shop01',True); core.tick()
            core.engine.transition(self.eid,'pause')
            with self.assertRaises(ValueError):core.fetch('shop01',self.eid,'event1')
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db')
            core.engine.transition(self.eid,'start'); core.health('shop01',True); core.tick()
            core.accept('shop01',self.eid,'event1')
            with self.assertRaises(ValueError):core.accept('shop01',self.eid,'event1')
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db')
            core.engine.transition(self.eid,'start'); core.health('shop01',True); core.tick()
            self.now+=9
            with self.assertRaises(ValueError):core.fetch('shop01',self.eid,'event1')

    def test_queue_failure_is_uncertain_and_never_retried(self):
        calls=[]
        def broken(event):calls.append(event);raise OSError('uncertain API response')
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db',broken)
            core.engine.transition(self.eid,'start'); core.health('shop01',True)
            core.tick();core.tick()
            self.assertEqual(len(calls),1)
            with self.assertRaises(ValueError):core.fetch('shop01',self.eid,'event1')

    def test_restart_pauses_and_revokes_future_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            core=self.make_core(pathlib.Path(tmp)/'state.db')
            core.engine.transition(self.eid,'start'); core.health('shop01',True);core.tick()
            core.engine.recover_restart()
            with self.assertRaises(ValueError):core.fetch('shop01',self.eid,'event1')
            core.tick();self.assertEqual(len(self.events),1)

if __name__=='__main__':unittest.main()
