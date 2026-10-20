import unittest
class FinishTests(unittest.TestCase):
    def test_snapshot_rejects_symlink_parent_escape(self):
        from finish_helpers import safe_path
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(safe_path(root/'new.txt'),root/'new.txt')
            try: (root/'redirect').symlink_to(root,target_is_directory=True)
            except OSError as error:
                if getattr(error,'winerror',None)==1314: self.skipTest('Run symlink guard on AlmaLinux')
                raise
            with self.assertRaises(ValueError): safe_path(root/'redirect'/'new.txt')

    def test_ssh_repair_preserves_comments_and_includes(self):
        from finish_helpers import ssh_repair
        text='# Keep this comment\nPermitRootLogin yes\nPermitEmptyPasswords yes\nInclude /etc/ssh/sshd_config.d/*.conf\n'
        result=ssh_repair(text)
        self.assertIn('Include /etc/ssh/sshd_config.d/*.conf\n',result)
        self.assertIn('# Keep this comment\n',result)
        self.assertNotIn('PermitRootLogin yes',result)
        self.assertIn('PermitRootLogin no\n',result)
        self.assertIn('competitor-recovery',result)
        with self.assertRaises(ValueError): ssh_repair(text+'Match User other\n')


class RollbackTests(unittest.TestCase):
    def test_new_competitor_content_is_preserved_and_restore_continues(self):
        from finish_helpers import restore_entry
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); documents=root/'Documents'; documents.mkdir()
            (documents/'business.txt').write_text('Real user content')
            self.assertFalse(restore_entry(documents,root/'saved',False,True,None))
            self.assertEqual((documents/'business.txt').read_text(),'Real user content')
            generated=root/'generated.conf'; generated.write_text('temporary')
            self.assertTrue(restore_entry(generated,root/'absent',False,False,None))
            self.assertFalse(generated.exists())

    def test_metadata_only_restore_does_not_overwrite_user_document(self):
        from finish_helpers import restore_entry
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); documents=root/'Documents'; documents.mkdir(); saved=root/'saved'; saved.mkdir()
            (documents/'business.txt').write_text('new work'); (saved/'business.txt').write_text('old work')
            calls=[]
            def run(args,**kwargs): calls.append(args); return 'user::rwx\ngroup::---\nother::---'
            self.assertTrue(restore_entry(documents,saved,True,True,run))
            self.assertEqual((documents/'business.txt').read_text(),'new work')
            self.assertFalse(any(args[0]=='cp' for args in calls))
            self.assertTrue(any(args[0]=='setfacl' for args in calls))


class IdentityRollbackTests(unittest.TestCase):
    def test_rollback_preserves_new_real_password_and_restores_only_training(self):
        from finish_helpers import restore_training_identity
        old=b'jwang:old:rest\nsummit-unknown:original:rest\n'
        current=b'jwang:new:rest\nsummit-unknown:locked:rest\nnew-real-user:value:rest\n'
        self.assertEqual(restore_training_identity(old,current,'shadow'),b'jwang:new:rest\nsummit-unknown:original:rest\nnew-real-user:value:rest\n')

    def test_wheel_rollback_retains_new_real_member(self):
        from finish_helpers import restore_training_identity
        old=b'wheel:x:10:jwang,summit-employee\n'
        current=b'wheel:x:10:jwang,new-admin\n'
        self.assertEqual(restore_training_identity(old,current,'group'),b'wheel:x:10:jwang,new-admin,summit-employee\n')


class AtomicIdentityTests(unittest.TestCase):
    def test_locked_atomic_restore_and_lock_release(self):
        import ast,os,pathlib,shutil,tempfile
        from unittest.mock import Mock,patch
        from finish_helpers import safe_path,restore_training_identity
        source=pathlib.Path(__file__).with_name('finish_workstation.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='restore_identity')
        namespace=dict(pathlib=pathlib,os=os,safe_path=safe_path,restore_training_identity=restore_training_identity)
        namespace['call']=lambda args: shutil.copy2(args[2],args[3])
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<identity-controller>','exec'),namespace)
        libc=Mock(); libc.lckpwdf.return_value=0
        with tempfile.TemporaryDirectory() as folder,patch('ctypes.CDLL',return_value=libc):
            root=pathlib.Path(folder)
            originals={name:b'jwang:old:rest\nsummit-unknown:original:rest\n' for name in ('passwd','shadow','group','gshadow')}
            for name in originals: (root/name).write_bytes(b'jwang:new:rest\nsummit-unknown:weak:rest\n')
            namespace['restore_identity'](originals,root)
            self.assertEqual((root/'shadow').read_bytes(),b'jwang:new:rest\nsummit-unknown:original:rest\n')
            self.assertFalse(list(root.glob('*.lock')))
            self.assertFalse(list(root.glob('.summit-identity-*')))
            self.assertEqual(libc.ulckpwdf.call_count,1)
            (root/'shadow.lock').write_text('other process')
            before={name:(root/name).read_bytes() for name in originals}
            with self.assertRaises(FileExistsError): namespace['restore_identity'](originals,root)
            self.assertEqual({name:(root/name).read_bytes() for name in originals},before)
            self.assertEqual((root/'shadow.lock').read_text(),'other process')
            self.assertFalse((root/'passwd.lock').exists())
            self.assertEqual(libc.ulckpwdf.call_count,2)


class RetryTests(unittest.TestCase):
    def test_zone_name_obeys_installed_firewalld_limit(self):
        from finish_helpers import valid_zone_name
        self.assertFalse(valid_zone_name('summit-workstation'))
        self.assertTrue(valid_zone_name('summit-ws01'))
        self.assertFalse(valid_zone_name('bad/name'))

    def test_retry_retains_known_failure_and_rejects_unverified_or_completed(self):
        from finish_helpers import choose_finish_backup
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)/'finish'
            self.assertEqual(choose_finish_backup(base),(base,[]))
            (base/'initial').mkdir(parents=True)
            (base/'initial/index.json').write_text('{}')
            failure=base/'failure.txt'; failure.write_text('unverified error')
            with self.assertRaises(ValueError): choose_finish_backup(base)
            failure.write_text("Error: INVALID_NAME: Zone 'summit-workstation': name has 18 chars, max is 17")
            self.assertEqual(choose_finish_backup(base),(base.with_name('finish-retry1'),[base]))
            self.assertTrue(failure.exists())
            (base/'rollback-failure.txt').write_text('error')
            with self.assertRaises(ValueError): choose_finish_backup(base)
            (base/'rollback-failure.txt').unlink(); (base/'completed.json').write_text('{}')
            with self.assertRaises(ValueError): choose_finish_backup(base)


class UnitStateTests(unittest.TestCase):
    def test_only_known_oneshot_uses_durable_state_and_failures_are_rejected(self):
        from finish_helpers import unit_state_matches
        old={'LoadState':'loaded','UnitFileState':'static','ActiveState':'active'}
        new=dict(old,ActiveState='inactive',Type='oneshot')
        self.assertTrue(unit_state_matches('summit-marker.service',new,old))
        self.assertFalse(unit_state_matches('summit-aeacus.service',new,old))
        self.assertFalse(unit_state_matches('summit-marker.service',dict(new,ActiveState='failed'),old))
        self.assertFalse(unit_state_matches('summit-marker.service',dict(new,Type='simple'),old))
        self.assertFalse(unit_state_matches('summit-marker.service',dict(new,UnitFileState='disabled'),old))


class MarkerRecoveryTests(unittest.TestCase):
    def test_only_pinned_unprivileged_sigterm_marker_is_restarted(self):
        import ast,contextlib,hashlib,io,json,pathlib,re,tempfile
        source=pathlib.Path(__file__).with_name('finish_workstation.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='ensure_marker_ready')
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); script=root/'marker.sh'; script.write_bytes(b'inert fixture')
            (root/'artifact-hashes.json').write_text(json.dumps({'systemd-marker.sh':hashlib.sha256(script.read_bytes()).hexdigest()}))
            info={'Type':'oneshot','User':'summit-marker-runner','Group':'summit-marker-runner','NoNewPrivileges':'yes','ProtectSystem':'strict','ProtectHome':'yes','PrivateTmp':'yes','DropInPaths':'','Result':'signal','ExecMainStatus':'15','ExecMainCode':'2','ActiveState':'failed','ExecStart':'{ path='+str(script)+' ; argv[]='+str(script)+' ; }'}
            calls=[]
            def run(args):
                calls.append(args)
                if args[:2]==['systemctl','show']: return '\n'.join(k+'='+v for k,v in info.items())
                if args==['systemctl','start','summit-marker.service']: info.update(Result='success',ExecMainStatus='0',ActiveState='inactive')
                return ''
            namespace=dict(call=run,states=lambda:{'summit-marker.timer':{'ActiveState':'active'}},safe_path=lambda unused:script,RES=root,hashlib=hashlib,json=json,re=re)
            exec(compile(ast.Module(body=[function],type_ignores=[]),'<marker-controller>','exec'),namespace)
            with contextlib.redirect_stdout(io.StringIO()): namespace['ensure_marker_ready']()
            changes=[args for args in calls if args[:2]!=['systemctl','show']]
            self.assertEqual(changes,[['systemctl','stop','summit-marker.timer'],['systemctl','stop','summit-marker.service'],['systemctl','reset-failed','summit-marker.service'],['systemctl','start','summit-marker.service'],['systemctl','start','summit-marker.timer']])
            calls.clear(); info.update(Result='exit-code',ExecMainStatus='1',ActiveState='failed')
            with self.assertRaises(AssertionError): namespace['ensure_marker_ready']()
            self.assertFalse(any(args[1] in ('start','stop') for args in calls))
            calls.clear(); info.update(Result='signal',ExecMainStatus='15',User='root')
            with self.assertRaises(AssertionError): namespace['ensure_marker_ready']()
            self.assertFalse(any(args[1] in ('start','stop') for args in calls))
            calls.clear(); info['User']='summit-marker-runner'; script.write_bytes(b'changed payload')
            with self.assertRaises(AssertionError): namespace['ensure_marker_ready']()
            self.assertFalse(any(args[1] in ('start','stop') for args in calls))


class MarkerGarbageCollectionTests(unittest.TestCase):
    def test_inactive_stopped_oneshot_does_not_require_reset_failed(self):
        import ast,contextlib,hashlib,io,json,pathlib,re,tempfile
        source=pathlib.Path(__file__).with_name('finish_workstation.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='ensure_marker_ready')
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); script=root/'marker.sh'; script.write_bytes(b'inert fixture')
            (root/'artifact-hashes.json').write_text(json.dumps({'systemd-marker.sh':hashlib.sha256(script.read_bytes()).hexdigest()}))
            info={'Type':'oneshot','User':'summit-marker-runner','Group':'summit-marker-runner','NoNewPrivileges':'yes','ProtectSystem':'strict','ProtectHome':'yes','PrivateTmp':'yes','DropInPaths':'','Result':'success','ExecMainStatus':'0','ExecMainCode':'1','ActiveState':'inactive','ExecStart':'{ path='+str(script)+' ; argv[]='+str(script)+' ; }'}
            calls=[]
            def run(args):
                calls.append(args)
                if args[1]=='show': return '\n'.join(k+'='+v for k,v in info.items())
                if args[1]=='reset-failed': raise RuntimeError('Unit not loaded')
                return ''
            namespace=dict(call=run,states=lambda:{'summit-marker.timer':{'ActiveState':'inactive'}},safe_path=lambda unused:script,RES=root,hashlib=hashlib,json=json,re=re)
            exec(compile(ast.Module(body=[function],type_ignores=[]),'<marker-gc-controller>','exec'),namespace)
            with contextlib.redirect_stdout(io.StringIO()): namespace['ensure_marker_ready'](force=True)
            self.assertIn(['systemctl','start','summit-marker.service'],calls)
            self.assertFalse(any(args[1]=='reset-failed' for args in calls))


class SavedRecoveryTests(unittest.TestCase):
    def test_saved_snapshot_cannot_expand_scope_or_escape_private_copies(self):
        from finish_helpers import validated_snapshot_entries
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); bank=root/'bank'; bank.mkdir(); target=root/'config'; saved=bank/'0'; saved.write_text('saved')
            item={'target':str(target),'saved':str(saved),'existed':True,'metadata_only':False}
            self.assertEqual(validated_snapshot_entries(bank,{'entries':[item]},[target]),[(target,saved,True,False)])
            with self.assertRaises(ValueError): validated_snapshot_entries(bank,{'entries':[dict(item,target=str(root/'foreign'))]},[target])
            with self.assertRaises(ValueError): validated_snapshot_entries(bank,{'entries':[dict(item,saved=str(root/'escape'))]},[target])
            with self.assertRaises(ValueError): validated_snapshot_entries(bank,{'entries':[dict(item,existed='true')]},[target])
            saved.unlink()
            with self.assertRaises(ValueError): validated_snapshot_entries(bank,{'entries':[item]},[target])

    def test_recovery_receipt_preserves_error_and_requires_verified_score(self):
        from finish_helpers import choose_finish_backup
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)/'finish'; (base/'initial').mkdir(parents=True)
            (base/'initial/index.json').write_text('{}'); (base/'failure.txt').write_text('failed restore')
            failure=base/'rollback-failure.txt'; failure.write_text('historical error')
            receipt=base/'recovery-verified.json'; receipt.write_text('{}')
            with self.assertRaises(ValueError): choose_finish_backup(base)
            receipt.write_text('{"verified":true,"score":0}')
            with self.assertRaises(ValueError): choose_finish_backup(base)
            receipt.write_text('{"verified":true,"score":6}')
            self.assertEqual(choose_finish_backup(base),(base.with_name('finish-retry1'),[base]))
            self.assertEqual(failure.read_text(),'historical error')


class EngineCompatibilityTests(unittest.TestCase):
    def test_private_preflight_uses_plaintext_cli_then_encrypted_runtime(self):
        import ast,contextlib,io,pathlib,shutil,tempfile,re
        source=pathlib.Path(__file__).with_name('finish_workstation.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='engine_compatibility')
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder); resources=root/'resources'; resources.mkdir(); production=root/'production'; (production/'assets').mkdir(parents=True)
            (production/'assets/ScoringReport.html').write_text('original production report')
            config=pathlib.Path(__file__).with_name('probe-validation-scoring.conf').read_text()
            (resources/'probe-validation-scoring.conf').write_text(config)
            actions=[]
            def write(path,text,mode): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text); path.chmod(mode)
            def run(args,**kwargs):
                if args[0]=='cp': shutil.copytree(args[2],args[3]); return ''
                directory=pathlib.Path(args[2]); action=args[-1]
                self.assertEqual(kwargs.get('cwd'),directory)
                self.assertEqual(directory,resources/'engine-compatibility')
                encrypted=not (directory/'scoring.conf').exists()
                actions.append((action,encrypted))
                if encrypted: raise RuntimeError('aeacus requires scoring.conf')
                text=(directory/'scoring.conf').read_text()
                self.assertEqual(re.findall(r'^cmd = .*$',text,re.M),['cmd = "/usr/bin/printf FAIL"']*40)
                if action=='readme': (directory/'assets/ReadMe.html').write_text((kwargs['cwd']/'ReadMe.conf').read_text())
                if action=='score': (directory/'assets/ScoringReport.html').write_text('0 out of 100 points received')
                if action=='encrypt': (directory/'scoring.dat').write_text('encrypted fixture')
                return 'OK'
            def encrypted_runtime(directory,binary):
                self.assertFalse((directory/'scoring.conf').exists())
                self.assertEqual((directory/'scoring.dat').read_text(),'encrypted fixture')
                self.assertEqual(binary,production/'phocus')
                actions.append(('phocus',True))
                (directory/'assets/ScoringReport.html').write_text('0 out of 100 points received')
            namespace=dict(RES=resources,ROOT=production,call=run,write=write,re=re,private_phocus=encrypted_runtime)
            exec(compile(ast.Module(body=[function],type_ignores=[]),'<engine-preflight>','exec'),namespace)
            with contextlib.redirect_stdout(io.StringIO()): namespace['engine_compatibility']()
            self.assertEqual(actions,[('check',False),('readme',False),('score',False),('encrypt',False),('phocus',True)])
            self.assertEqual((production/'assets/ScoringReport.html').read_text(),'original production report')


class EncryptedRuntimeTests(unittest.TestCase):
    def test_report_requires_complete_html_correct_total_and_live_runtime(self):
        import pathlib,tempfile
        from finish_helpers import wait_scoring_report
        with tempfile.TemporaryDirectory() as folder:
            report=pathlib.Path(folder)/'report'
            report.write_text('0 out of 100 points received; 0 out of 40 scored security issues fixed </html>')
            wait_scoring_report(report,lambda:True)
            with self.assertRaisesRegex(RuntimeError,'exited'): wait_scoring_report(report,lambda:False)
            report.write_text('30 out of 30 points received </html>')
            with self.assertRaisesRegex(RuntimeError,'differs'): wait_scoring_report(report,lambda:True)
            report.write_text('0 out of 100 points received; 0 out of 3 scored security issues fixed </html>')
            with self.assertRaisesRegex(RuntimeError,'differs'): wait_scoring_report(report,lambda:True)

    def test_partial_or_missing_report_cannot_pass_and_wait_is_bounded(self):
        import pathlib,tempfile
        from unittest.mock import patch
        from finish_helpers import wait_scoring_report
        with tempfile.TemporaryDirectory() as folder:
            report=pathlib.Path(folder)/'report'
            for present in (False,True):
                if present: report.write_text('0 out of 100 points received; 0 out of 40 scored security issues fixed')
                with patch('time.monotonic',side_effect=[0,0,2]),patch('time.sleep'):
                    with self.assertRaisesRegex(RuntimeError,'Timed out'): wait_scoring_report(report,lambda:True,timeout=1)

    def test_namespace_removes_stale_report_and_cleans_own_process_on_success_or_failure(self):
        import pathlib,tempfile,signal
        from unittest.mock import Mock,patch
        from finish_helpers import private_phocus
        with tempfile.TemporaryDirectory() as folder:
            directory=pathlib.Path(folder); (directory/'assets').mkdir(); binary=directory/'original'; binary.write_bytes(b'fixture')
            report=directory/'assets/ScoringReport.html'
            for failure in (False,True):
                report.write_text('stale report')
                process=Mock(pid=123456); process.poll.return_value=None
                def verify(path,alive):
                    self.assertEqual(path,report); self.assertFalse(report.exists()); self.assertTrue(alive())
                    if failure: raise RuntimeError('fixture failure')
                with patch('subprocess.Popen',return_value=process) as launch,patch('os.killpg',create=True) as kill,patch('finish_helpers.wait_scoring_report',side_effect=verify):
                    if failure:
                        with self.assertRaisesRegex(RuntimeError,'fixture failure'): private_phocus(directory,binary)
                    else: private_phocus(directory,binary)
                    args=launch.call_args.args[0]
                    self.assertEqual(args[:5],['/usr/bin/unshare','--mount','--propagation','private','/usr/bin/python3'])
                    self.assertTrue(launch.call_args.kwargs['start_new_session'])
                    self.assertEqual(args[-1],str(directory.resolve()))
                    self.assertIn("['/usr/bin/mount','--bind'",args[-2])
                    kill.assert_called_once_with(process.pid,signal.SIGTERM)
                    process.wait.assert_called_once_with(timeout=5)

    def test_production_verification_removes_report_before_restart_and_uses_no_plaintext_cli(self):
        import ast,pathlib
        source=pathlib.Path(__file__).with_name('finish_workstation.py').read_text()
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='install_runtime')
        body=ast.get_source_segment(source,function)
        after_removal=body.split("(ROOT/'scoring.conf').unlink()",1)[1]
        self.assertNotIn("ROOT/'aeacus'",after_removal)
        self.assertLess(body.index("(ROOT/'assets/ScoringReport.html').unlink()"),body.index("['systemctl','restart','summit-aeacus.service']"))
        self.assertIn("wait_scoring_report(ROOT/'assets/ScoringReport.html'",body)

if __name__=='__main__': unittest.main()
