import unittest
import permissions
from unittest.mock import patch

class PermissionTests(unittest.TestCase):
    def test_active_include_link_parent_must_be_protected(self):
        from types import SimpleNamespace
        with patch.object(permissions,'run',return_value=' (1) /etc/apache2/sites-enabled/summit-shop.conf\n'),\
             patch.object(permissions,'protected',return_value=True),\
             patch.object(permissions,'protected_reference',return_value=False,create=True),\
             patch.object(permissions,'result',return_value=SimpleNamespace(returncode=0)),\
             patch.object(permissions,'active',return_value=True):
            self.assertFalse(permissions.check(27))
    def test_empty_sudo_include_directory_is_still_protected(self):
        self.assertEqual(permissions.sudo_paths('/etc/sudoers: parsed OK\n'),{'/etc/sudoers','/etc/sudoers.d'})
        self.assertIn('/etc/sudoers.d',permissions.sudo_paths('visudo: /etc/sudoers.d is world writable\n/etc/sudoers: parsed OK\n'))

    def test_shadow_metadata_requires_existing_object(self):
        self.assertTrue(permissions.evaluate(25, {'protected':True,'mode':0o640,'group_ok':True}))
        self.assertFalse(permissions.evaluate(25, {'protected':False,'mode':0o640,'group_ok':True}))
        self.assertFalse(permissions.evaluate(25, {'protected':True,'mode':0o644,'group_ok':True}))

    def test_apache_and_content_need_healthy_service_and_all_paths(self):
        for n in (27,28):
            self.assertTrue(permissions.evaluate(n, {'protected_paths':[True,True], 'running':True,'syntax':True,'content_present':True}))
            self.assertFalse(permissions.evaluate(n, {'protected_paths':[True,False], 'running':True,'syntax':True,'content_present':True}))
            self.assertFalse(permissions.evaluate(n, {'protected_paths':[], 'running':True,'syntax':True,'content_present':True}))
            self.assertFalse(permissions.evaluate(n, {'protected_paths':[True], 'running':False,'syntax':True,'content_present':True}))

    def test_sudo_syntax_and_key_presence_required(self):
        self.assertFalse(permissions.evaluate(26, {'protected_paths':[True], 'syntax':False}))
        self.assertFalse(permissions.evaluate(29, {'protected':False,'running':True}))

if __name__ == '__main__': unittest.main()
