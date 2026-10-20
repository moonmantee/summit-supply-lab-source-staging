import unittest,os
from pathlib import Path
import tempfile
import contract
from unittest.mock import patch

class ContractTests(unittest.TestCase):
    def test_forensics_answer_section_only(self):
        self.assertEqual(contract.answer('Question: vendor\nAnswer:\n\n'), '')
        self.assertEqual(contract.answer('Question: wrong\nAnswer:\n  VENDOR  \n'), 'vendor')
        with self.assertRaises(ValueError): contract.answer('vendor')
        with self.assertRaises(ValueError): contract.answer('Answer:\na\nAnswer:\nb')

    def test_errors_are_not_weaknesses(self):
        with self.assertRaises(RuntimeError): contract.require_matrix(['ERROR'] * 30, 'FAIL')
        with self.assertRaises(RuntimeError): contract.require_matrix(['FAIL'] * 29, 'FAIL')
        contract.require_matrix(['PASS'] * 30, 'PASS')

    def test_effective_ssh_repeated_values_preserved(self):
        self.assertEqual(contract.parse_native('allowgroups a\nallowgroups b\n')['allowgroups'], ['a','b'])
        with self.assertRaises(ValueError): contract.parse_native('bad')

    def test_report_requires_complete_exact_score(self):
        good = '<html>0 out of 100 points received; 0 out of 30 scored security issues fixed</html>'
        contract.require_report(good, 0)
        for bad in (good.replace('30','29'),good.replace('100','90'),good[:-7],good.replace('0 out of 100','5 out of 100')):
            with self.assertRaises(ValueError): contract.require_report(bad,0)

    def test_backup_permissions_reject_acl_and_missing_data(self):
        self.assertTrue(contract.backup_acl_ok(0, 0o640, 'user::rw-\ngroup::r--\nother::---\n', True))
        self.assertFalse(contract.backup_acl_ok(0,0o644,'user::rw-\ngroup::r--\nother::r--\n',True))
        self.assertFalse(contract.backup_acl_ok(0,0o640,'user::rw-\nuser:1001:r--\ngroup::r--\nother::---\n',True))
        self.assertFalse(contract.backup_acl_ok(0,0o640,'user::rw-\ngroup::r--\nother::---\n',False))
        self.assertFalse(contract.backup_acl_ok(0,0o640,'user::rw-\ngroup::r--\nother::---\n',True,gid=1000))

    def test_disabled_is_not_enough_if_socket_still_active(self):
        self.assertTrue(contract.unit_safe({'ActiveState':'inactive','UnitFileState':'masked'}))
        self.assertFalse(contract.unit_safe({'ActiveState':'active','UnitFileState':'disabled'}))
        self.assertFalse(contract.unit_safe({'ActiveState':'inactive','UnitFileState':'enabled'}))
        with self.assertRaises(ValueError): contract.unit_safe({})

    def test_probe_command_errors_remain_errors(self):
        import probes
        with patch.object(probes,'check',side_effect=RuntimeError('native API unavailable')):
            self.assertEqual(probes.verdict(3),'ERROR')

    def test_roles_are_followed_through_nested_grants(self):
        import probes
        with patch.object(probes,'sql',return_value='shop_app\t10.77.30.10\touter\nouter\t\tinner\ninner\t\touter'):
            names=probes.effective_grantees('shop_app','10.77.30.10')
            self.assertIn('shop_app',names)
            self.assertIn('outer',names)
            self.assertIn('inner',names)

    @unittest.skipIf(os.name=='nt','Native Linux builder is tested on SQL01')
    def test_activation_is_blocked_before_stopping_discovery(self):
        import build_sql01
        actions=[]
        def native(args):
            action=args[1]
            if action=='stop' and not {'disable','mask'}<=set(actions):
                raise RuntimeError('Job for avahi-daemon.service canceled by activation')
            actions.append(action)
        with patch.object(build_sql01,'cmd',side_effect=native):
            build_sql01.service_state(('avahi-daemon.service','avahi-daemon.socket'),True)
        self.assertLess(actions.index('mask'),actions.index('stop'))

    @unittest.skipIf(os.name=='nt','Native Linux builder is tested on SQL01')
    def test_service_stop_failures_are_not_suppressed(self):
        import build_sql01
        def native(args):
            if args[1]=='stop': raise RuntimeError('Unrelated systemd failure')
        with patch.object(build_sql01,'cmd',side_effect=native):
            with self.assertRaisesRegex(RuntimeError,'Unrelated systemd failure'):
                build_sql01.service_state(('cups.service','cups.socket','cups.path'),True)

    def test_package_has_exact_manifest_and_lf_entry_point(self):
        import json,base64,zipfile,io,re
        base=Path(__file__).resolve().parent
        if not (base/'make-sql01-competition.sh').exists(): self.skipTest('outer package checked before deployment')
        source=(base/'make-sql01-competition.sh').read_bytes()
        self.assertNotIn(b'\r',source)
        match=re.search(rb"blob=base64.b64decode\('([^']+)'\)",source)
        self.assertIsNotNone(match)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(match.group(1)))) as archive:
            data=json.loads(archive.read('competition-manifest.json'))
            self.assertEqual(len(data['issues']),30)
            self.assertEqual(sum(i['points'] for i in data['issues']),100)
            self.assertEqual([i['id'] for i in data['issues']],list(range(1,31)))

if __name__ == '__main__': unittest.main()
