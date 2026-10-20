import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'legacy'))
from scheduler import Engine
from state import Store
from manifest import validate_scenario
from four_hours import build_four_hours
class ControllerTests(unittest.TestCase):
 def test_four_hour_lifecycle_and_duration_reaches_fixed_worker(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(pathlib.Path(d)/'state.sqlite3');clock=[0]
   eid=store.create_exercise(3,duration_s=14400);event=build_four_hours()[102]
   engine=Engine(store,[event],clock=lambda:clock[0],wall_clock=lambda:100)
   engine.transition(eid,'start');clock[0]=10803
   delivered=engine.next_event(eid,'shop01',{'id':3,'state':'RUNNING'})
   self.assertEqual(delivered['duration'],180);self.assertEqual(delivered['expires'],112)
   clock[0]=14400;engine.heartbeat({'id':3,'state':'RUNNING'});self.assertEqual(store.status(eid)['state'],'FINISHED')
 def test_legacy_manifest_routes_only_new_closed_actions(self):
  e=build_four_hours()[102];self.assertEqual(validate_scenario([e],{'shop01':['apache']}),[e])
  with self.assertRaises(ValueError):validate_scenario([{**e,'action':'arbitrary_shell'}],{'shop01':['apache']})
 def test_historical_three_hour_manifest_keeps_old_cap(self):
  e={**build_four_hours()[72],'at':11000}
  with self.assertRaises(ValueError):validate_scenario([e],{'shop01':['apache']})
if __name__=='__main__':unittest.main()
