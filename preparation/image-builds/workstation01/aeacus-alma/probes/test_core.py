import unittest

from core import evaluate


class CoreScoringTests(unittest.TestCase):
    def test_ssh_exception_in_one_context_blocks_credit(self):
        for issue,key in ((5,'permitrootlogin'),(6,'permitemptypasswords')):
            self.assertTrue(evaluate(issue,{'ssh_contexts':[key+' no',key+' no']}))
            self.assertFalse(evaluate(issue,{'ssh_contexts':[key+' no',key+' yes']}))
            self.assertFalse(evaluate(issue,{'ssh_contexts':[key+' no',None]}))
            self.assertFalse(evaluate(issue,{'ssh_contexts':[]}))

    def test_root_ssh_context_must_deny_root(self):
        self.assertTrue(evaluate(5, {'ssh': 'permitrootlogin no\n'}))
        self.assertFalse(evaluate(5, {'ssh': 'permitrootlogin yes\n'}))
        self.assertFalse(evaluate(5, {'ssh': 'permitrootlogin prohibit-password\n'}))

    def test_missing_or_failed_ssh_never_awards_points(self):
        for data in ({}, {'ssh': ''}, {'ssh': None}, {'ssh': 'permitrootlogin no\npermitrootlogin yes\n'}):
            self.assertFalse(evaluate(5, data))

    def test_empty_password_setting_is_independent(self):
        self.assertTrue(evaluate(6, {'ssh': 'permitemptypasswords no\npermitrootlogin yes\n'}))
        self.assertFalse(evaluate(6, {'ssh': 'permitemptypasswords yes\n'}))

    def test_selinux_requires_runtime_and_boot_enforcement(self):
        clean = {'selinux': 'Enforcing', 'selinux_config': 'SELINUX=enforcing\n', 'cmdline': 'quiet rhgb'}
        self.assertTrue(evaluate(16, clean))
        for key, value in [('selinux', 'Permissive'), ('selinux_config', 'SELINUX=permissive'), ('cmdline', 'quiet selinux=0'), ('cmdline', 'enforcing=0'), ('cmdline', None)]:
            self.assertFalse(evaluate(16, dict(clean, **{key: value})))

    def test_commented_selinux_setting_is_not_effective(self):
        self.assertFalse(evaluate(16, {'selinux': 'Enforcing', 'selinux_config': '# SELINUX=enforcing', 'cmdline': 'quiet'}))

    def test_socket_activation_prevents_service_credit(self):
        clean = {'units': [{'LoadState': 'loaded', 'ActiveState': 'inactive', 'UnitFileState': 'disabled'}] * 3, 'process_absent': True}
        self.assertTrue(evaluate(30, clean))
        self.assertFalse(evaluate(30, dict(clean, units=[clean['units'][0], {'LoadState': 'loaded', 'ActiveState': 'active', 'UnitFileState': 'enabled'}, clean['units'][0]])))
        self.assertFalse(evaluate(30, dict(clean, process_absent=False)))
        self.assertFalse(evaluate(30, dict(clean, units=clean['units'][:2])))

    def test_service_removed_is_valid_but_unknown_state_is_not(self):
        self.assertTrue(evaluate(29, {'units': [{'LoadState': 'not-found', 'ActiveState': 'inactive', 'UnitFileState': ''}] * 2, 'process_absent': True}))
        self.assertFalse(evaluate(29, {'units': [{}, {}], 'process_absent': True}))
        self.assertFalse(evaluate(29, {'units': [{'LoadState': 'loaded', 'ActiveState': 'inactive', 'UnitFileState': 'static'}] * 2, 'process_absent': True}))

    def test_tmp_requires_directory_owner_mode_and_label(self):
        clean = {'tmp_stat': '1777 0 0 directory', 'tmp_label': 'system_u:object_r:tmp_t:s0 /tmp'}
        self.assertTrue(evaluate(32, clean))
        for key, value in [('tmp_stat', '777 0 0 directory'), ('tmp_stat', '1777 1000 1000 directory'), ('tmp_stat', '1777 0 0 symbolic link'), ('tmp_label', '? /tmp')]:
            self.assertFalse(evaluate(32, dict(clean, **{key: value})))

    def test_unknown_issue_never_awards_points(self):
        self.assertFalse(evaluate(999, {}))


if __name__ == '__main__':
    unittest.main()
