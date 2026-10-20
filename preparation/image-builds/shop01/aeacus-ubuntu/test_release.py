import copy
import unittest
import release_helpers as h


class ReleaseTests(unittest.TestCase):
    def test_private_candidate_can_bind_final_probe_runtime_without_host_mutation(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch,MagicMock
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); candidate=root/'candidate'; (candidate/'assets').mkdir(parents=True)
            binary=root/'binary'; binary.write_text('fixture')
            runtime=root/'runtime'; runtime.mkdir()
            process=MagicMock(); process.pid=123456
            with patch('subprocess.Popen',return_value=process) as launch, patch('os.killpg',create=True), \
                 patch.object(h,'wait_scoring_report'):
                h.private_phocus(candidate,binary,runtime=runtime)
            args=launch.call_args.args[0]
            self.assertIn('/opt/summit-shop01',args[6])
            self.assertEqual(args[-1],str(runtime.resolve()))

    def test_encrypted_report_waits_for_complete_fresh_html_and_live_process(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report.html'
            good='0 out of 100 points received 0 out of 40 scored security issues fixed'
            report.write_text(good+'</html>')
            h.wait_scoring_report(report,lambda:True,timeout=1)
            with self.assertRaises(RuntimeError): h.wait_scoring_report(report,lambda:False,timeout=1)
            report.write_text(good)
            with self.assertRaises(RuntimeError): h.wait_scoring_report(report,lambda:True,timeout=0.01)
            report.write_text('1 out of 100 points received 0 out of 40 scored security issues fixed</html>')
            with self.assertRaises(ValueError): h.wait_scoring_report(report,lambda:True,timeout=1)

    def test_isolated_phocus_failure_terminates_only_its_process_group(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch,MagicMock
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); candidate=root/'candidate'; (candidate/'assets').mkdir(parents=True)
            binary=root/'phocus'; binary.write_text('fixture')
            report=candidate/'assets/ScoringReport.html'; report.write_text('stale')
            process=MagicMock(); process.pid=123456
            with patch('subprocess.Popen',return_value=process) as launch, patch('os.killpg',create=True) as kill, \
                 patch.object(h,'wait_scoring_report',side_effect=RuntimeError('injected')):
                with self.assertRaises(RuntimeError): h.private_phocus(candidate,binary)
            self.assertFalse(report.exists())
            args=launch.call_args.args[0]
            self.assertEqual(args[:4],['/usr/bin/unshare','--mount','--propagation','private'])
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(kill.call_args.args[0],123456)
            process.wait.assert_called_once_with(timeout=5)

    def test_native_command_reads_readme_from_isolated_candidate_cwd(self):
        import importlib.util
        import tempfile
        import sys
        from pathlib import Path
        path=Path(__file__).parent/'deploy-scoring.py'
        spec=importlib.util.spec_from_file_location('deploy_under_test',path)
        deploy=importlib.util.module_from_spec(spec); spec.loader.exec_module(deploy)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); candidate=root/'candidate'; candidate.mkdir()
            (candidate/'ReadMe.conf').write_text('isolated-readme-fixture')
            deploy.BACKUP=root
            command=[sys.executable,'-c',"from pathlib import Path; print(Path('ReadMe.conf').read_text())"]
            try:
                try: output=deploy.call(command,cwd=candidate)
                except TypeError: output=deploy.call(command)
            except RuntimeError: output='wrong working directory'
            self.assertEqual(output.strip(),'isolated-readme-fixture')
    def test_existing_viewer_is_checked_in_its_user_service_scope(self):
        check=getattr(h,'require_user_viewer',lambda run,uid:run(['systemctl','is-active','summit-report-viewer']))
        seen=[]
        def run(args):
            seen.append(args)
            if '--user' not in args or 'XDG_RUNTIME_DIR=/run/user/1000' not in args:
                raise RuntimeError('System service is absent; user viewer is active')
            return 'active\n'
        check(run,1000)
        self.assertEqual(len(seen),1)
    def test_early_cutover_failures_resume_scorer_and_remove_partial_runtime(self):
        transaction=getattr(h,'cutover_transaction',lambda **kwargs:None)
        for failure in ('prepare','stop','snapshot','apply'):
            events=[]
            def action(name):
                def invoke(*args):
                    events.append(name)
                    if name==failure: raise RuntimeError('injected failure')
                    return 'candidate'
                return invoke
            with self.assertRaises(RuntimeError):
                transaction(**{name:action(name) for name in ('prepare','stop','snapshot','apply','rollback','resume','cleanup')})
            self.assertIn('cleanup',events)
            if failure in ('stop','snapshot'): self.assertIn('resume',events)
            if failure=='apply': self.assertIn('rollback',events)
    def evidence(self):
        def state(secure):
            return {'count':40,'total_points':100,'expected_points':100 if secure else 0,
                    'checks':[{'id':i,'status':'PASS' if secure else 'FAIL'} for i in range(1,41)]}
        return {'repaired':state(True),'restored':state(False)}

    def test_requires_both_full_rehearsal_states(self):
        h.require_rehearsal(self.evidence())
        for part in ('repaired','restored'):
            bad=copy.deepcopy(self.evidence()); bad[part]['checks'][8]['status']='ERROR'
            with self.assertRaises(ValueError): h.require_rehearsal(bad)

    def test_report_requires_correct_score_and_objective_count(self):
        good='0 out of 100 points received 0 out of 40 scored security issues fixed'
        h.require_report(good)
        for bad in ('0 out of 10 points received 0 out of 5 scored security issues fixed',
                    '2 out of 100 points received 1 out of 40 scored security issues fixed',
                    '0 out of 100 points received'):
            with self.assertRaises(ValueError): h.require_report(bad)


if __name__=='__main__': unittest.main()
