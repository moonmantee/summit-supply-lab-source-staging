import pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

class FirstThreeHoursTests(unittest.TestCase):
    def test_recovery_cannot_complete_while_mutation_is_in_flight(self):
        import threading
        from business_actions import Actions
        entered=threading.Event();release=threading.Event();restored=threading.Event();errors=[];now=[100.0]
        class Backend:
            def ready(self):return True
            def apply(self,*args):entered.set();assert release.wait(3)
            def observe_repair(self):restored.set();return True
        with tempfile.TemporaryDirectory() as temp:
            actions=Actions(pathlib.Path(temp)/'records.db',Backend(),lambda:now[0],lambda:now[0],lambda:'boot')
            event={'exercise':'one','id':'two','guest':'shop01','action':'business_stop','target':'apache','duration':15,'expires':110}
            def apply():
                try:actions.apply(event)
                except Exception as error:errors.append(error)
            first=threading.Thread(target=apply);first.start();self.assertTrue(entered.wait(2));now[0]=120
            second=threading.Thread(target=actions.recover);second.start()
            self.assertFalse(restored.wait(0.2));release.set();first.join(3);second.join(3)
            self.assertFalse(errors);self.assertTrue(restored.is_set());self.assertEqual(actions.status()[0]['phase'],'REPAIRED')
    def test_only_notices_then_stops_then_startup_restart_changes(self):
        from first_three_hours import build_schedule,validate
        events=build_schedule('shop01','apache')
        self.assertEqual(len(events),24)
        self.assertEqual(validate(events,{'shop01':{'apache'}}),events)
        for event in events:
            self.assertLess(event['at'],10800)
            if event['at']<3600:self.assertEqual(event['action'],'notice')
            elif event['at']<7200:self.assertEqual(event['action'],'business_stop')
            else:self.assertIn(event['action'],('business_disable','business_restart_off'))
        faults=[e for e in events if e['action']!='notice']
        self.assertTrue(all(e['duration']==180 for e in faults))
        for a,b in zip(faults,faults[1:]):self.assertGreaterEqual(b['at'],a['at']+a['window']+a['duration']+30)
        self.assertLessEqual(faults[-1]['at']+faults[-1]['window']+faults[-1]['duration']+30,10800)

    def test_binary_config_and_unapproved_targets_fail_validation(self):
        from first_three_hours import build_schedule,validate
        event=build_schedule('shop01','apache')[12]
        for updates in ({'action':'service_executable'},{'action':'service_config'},
                        {'target':'ssh'},{'at':10800},{'duration':181},{'command':'id'}):
            with self.assertRaises(ValueError):validate([{**event,**updates}],{'shop01':{'apache'}})

    def test_coordinator_reserves_duration_and_finishes_at_three_hours(self):
        sys.path.insert(0,str(ROOT/'legacy'))
        from first_three_hours import build_schedule
        from manifest import validate_scenario
        from state import Store
        from scheduler import Engine
        from fixture_coordinator import Core
        with tempfile.TemporaryDirectory() as temp:
            now=[100.0];events=[{**build_schedule('shop01','apache')[12],'at':0}]
            validate_scenario(events,{'shop01':['apache']})
            store=Store(pathlib.Path(temp)/'state.db');eid=store.create_exercise(3,duration_s=10800)
            engine=Engine(store,events,clock=lambda:now[0],wall_clock=lambda:now[0])
            queued=[];core=Core(engine,lambda:{'id':3,'state':'RUNNING'},lambda e:queued.append(e) or 'link',{'shop01':{}},clock=lambda:now[0])
            engine.transition(eid,'start');core.health('shop01',True);core.tick()
            self.assertEqual(queued[0]['duration'],180)
            with store.transaction() as db:self.assertEqual(db.execute('SELECT busy_until FROM caldera_links').fetchone()[0],300)
            now[0]+=10800;core.tick();self.assertEqual(store.status(eid)['state'],'FINISHED')

    def test_passive_observation_survives_restart_and_preserves_policy_replacement(self):
        from business_actions import Actions
        class Backend:
            healthy=True;mode='normal';changed=False
            def ready(self):return self.healthy and self.mode=='normal' and not self.changed
            def apply(self,action,expires):self.healthy=False;self.mode=action
            def observe_repair(self):
                if self.changed:raise ValueError('Competitor replacement')
                return self.ready()
        with tempfile.TemporaryDirectory() as temp:
            backend=Backend();now=[100.0]
            actions=Actions(pathlib.Path(temp)/'records.db',backend,lambda:now[0],lambda:now[0],lambda:'boot1')
            event={'exercise':'one','id':'two','guest':'shop01','action':'business_restart_off','target':'apache','duration':180,'expires':110}
            actions.apply(event);self.assertFalse(backend.ready())
            with self.assertRaises(ValueError):actions.apply(event)
            now[0]=281
            Actions(pathlib.Path(temp)/'records.db',backend,lambda:now[0],lambda:now[0],lambda:'boot1').recover()
            self.assertFalse(backend.ready());self.assertEqual(actions.status()[0]['phase'],'APPLIED')
            backend.mode='normal';backend.healthy=True;actions.recover()
            self.assertEqual(actions.status()[0]['phase'],'REPAIRED')
            event.update(id='three',expires=290);actions.apply(event);backend.changed=True;now[0]=462
            actions.recover();self.assertFalse(backend.healthy)
            self.assertEqual(actions.status()[-1]['phase'],'APPLIED')

    def test_expired_event_cannot_mutate_and_failed_apply_remains_recoverable(self):
        from business_actions import Actions
        class Backend:
            calls=0;healthy=True
            def ready(self):return self.healthy
            def apply(self,*args):self.calls+=1;self.healthy=False;raise OSError('Interrupted after policy mutation')
            def observe_repair(self):return self.healthy
        with tempfile.TemporaryDirectory() as temp:
            backend=Backend();now=[100.0]
            actions=Actions(pathlib.Path(temp)/'records.db',backend,lambda:now[0],lambda:now[0],lambda:'boot')
            event={'exercise':'one','id':'two','guest':'shop01','action':'business_disable','target':'apache','duration':180,'expires':99}
            with self.assertRaises(ValueError):actions.apply(event)
            self.assertEqual(backend.calls,0)
            event['expires']=110
            with self.assertRaises(OSError):actions.apply(event)
            self.assertEqual(actions.status()[0]['phase'],'PREPARED')
            now[0]=281;actions.recover();self.assertEqual(backend.calls,1)
            self.assertEqual(actions.status()[0]['phase'],'PREPARED')
            backend.healthy=True;actions.recover();self.assertEqual(actions.status()[0]['phase'],'REPAIRED')

if __name__=='__main__':unittest.main()
