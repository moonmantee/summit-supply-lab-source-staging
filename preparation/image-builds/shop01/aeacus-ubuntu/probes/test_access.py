import unittest
from unittest.mock import patch
import access

class AccessTests(unittest.TestCase):
    def test_actual_proxyjump_source_is_evaluated(self):
        self.assertIn('10.77.30.1',access.SOURCES)

    def test_locked_employee_cannot_earn_age_credit(self):
        passwd='summit_employee:x:1001:1001::/home/summit_employee:/bin/bash'
        with patch.object(access,'read',side_effect=lambda p:passwd if str(p)=='/etc/passwd' else 'summit_employee:!$6$old$'+('A'*86)+':20000:0:90:7:::'):
            self.assertFalse(access.check(11))
    def test_native_multiline_ssh_roster_and_denials_are_all_evaluated(self):
        native='authorizedkeyscommand none\nallowusers jwang\nallowusers summit_editor\n'
        self.assertTrue(access.evaluate(14,{'running':True,'configs':[native]}))
        for override in ('denyusers contractor_lab\ndenyusers summit_editor\n',
                         'allowgroups sudo\nallowgroups employees\n',
                         'denygroups contractors\ndenygroups sudo\n',
                         'allowusers contractor_lab\n'):
            self.assertFalse(access.evaluate(14,{'running':True,'configs':[native+override]}))

    def test_malformed_replacement_hash_cannot_earn_credential_credit(self):
        passwd='summit_employee:x:1001:1001::/home/summit_employee:/bin/bash'
        original='$6$old$'+'A'*86
        for hashed in ('$garbage', '$6$salt$short', '!'+original, '*', ''):
            files={'/etc/passwd':passwd,'/etc/shadow':'summit_employee:'+hashed+':20000:0:90:7:::'}
            with patch.object(access,'read',side_effect=lambda p:files[str(p)]), patch.object(access,'private_metadata',return_value={'planted_employee_hash':original}):
                self.assertFalse(access.collect(6)['active_hash'],hashed)

    def test_ubuntu_nobody_is_a_system_identity_at_uid_65534(self):
        self.assertTrue(access.system_identity(['nobody','x','65534','65534','nobody','/nonexistent','/usr/sbin/nologin']))
        self.assertFalse(access.system_identity(['summit_employee','x','1001','1001','','/home/summit_employee','/bin/bash']))

    def test_uid_zero_requires_root_and_rejects_alias(self):
        self.assertTrue(access.evaluate(2, {'users': 'root:x:0:0::/root:/bin/bash\njwang:x:1000:1000::/home/jwang:/bin/bash'}))
        self.assertFalse(access.evaluate(2, {'users': 'root:x:0:0::/root:/bin/bash\nsummit_root:x:0:0::/root:/usr/sbin/nologin'}))
        self.assertFalse(access.evaluate(2, {'users': ''}))
        self.assertFalse(access.evaluate(2, {'users': 'root:x:0:0::/root:/bin/bash\nsummit_root:x:00:0::/root:/usr/sbin/nologin'}))

    def test_employee_group_repair_cannot_delete_account(self):
        self.assertTrue(access.evaluate(3, {'exists': True, 'groups': ['summit_employee']}))
        self.assertFalse(access.evaluate(3, {'exists': False, 'groups': []}))
        self.assertFalse(access.evaluate(3, {'exists': True, 'groups': ['sudo']}))

    def test_credential_repair_requires_active_retained_account(self):
        good = {'exists': True, 'active_hash': True, 'changed_hash': True, 'usable': True}
        self.assertTrue(access.evaluate(6, good))
        for name in good:
            bad = dict(good); bad[name] = False
            self.assertFalse(access.evaluate(6, bad))

    def test_password_age_rejects_disabled_or_missing(self):
        for age, want in [(0,False),(-1,False),(99999,False),(90,True),(14,True)]:
            self.assertEqual(access.evaluate(11, {'exists':True,'max_age':age,'usable':True,'active_hash':True}), want)

    def test_secure_ssh_value_requires_running_service(self):
        self.assertTrue(access.evaluate(12, {'running':True,'configs':['permitrootlogin no\n']}))
        self.assertFalse(access.evaluate(12, {'running':False,'configs':['permitrootlogin no\n']}))
        self.assertFalse(access.evaluate(12, {'running':True,'configs':['permitrootlogin no','permitrootlogin yes']}))

    def test_ssh_roster_must_match_and_have_no_alternate_key_command(self):
        good = {'running':True,'configs':['allowusers jwang summit_editor\nauthorizedkeyscommand none\n']}
        self.assertTrue(access.evaluate(14,good))
        for cfg in ['allowusers *\nauthorizedkeyscommand none', 'allowusers jwang summit_editor contractor_lab\nauthorizedkeyscommand none', 'allowusers jwang summit_editor\nauthorizedkeyscommand /tmp/helper']:
            self.assertFalse(access.evaluate(14, {'running':True,'configs':[cfg]}))

if __name__ == '__main__': unittest.main()
