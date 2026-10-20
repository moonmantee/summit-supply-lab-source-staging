"""Run existing controller/policy tests against the staged deployment sources."""
import importlib.util
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'payload/controller'));sys.path.insert(0,str(ROOT/'payload/controller/legacy'))
suite=unittest.TestSuite()
cases={
 'test_fixture_bridge':('FixtureTests',('test_command_accepts_identifiers_only','test_no_dispatch_without_fresh_broker_health','test_pause_event_switch_expiry_and_replay_refuse_authorization','test_queue_failure_is_uncertain_and_never_retried','test_restart_pauses_and_revokes_future_dispatch')),
 'test_first_three_hours':('FirstThreeHoursTests',('test_only_notices_then_stops_then_startup_restart_changes','test_binary_config_and_unapproved_targets_fail_validation','test_coordinator_reserves_duration_and_finishes_at_three_hours')),
 'test_controller_hour4':('ControllerTests',None),
 'test_stage_policy':('PolicyTests',None),
}
for name,(classname,methods) in cases.items():
    spec=importlib.util.spec_from_file_location(name,ROOT/'reference/regression'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if name=='test_stage_policy':module.ROOT=ROOT/'payload/caldera'
    cls=getattr(module,classname)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(cls) if methods is None else [cls(method) for method in methods])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
