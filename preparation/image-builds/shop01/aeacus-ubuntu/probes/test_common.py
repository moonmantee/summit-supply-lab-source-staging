import sys
import tempfile
import unittest
from pathlib import Path
import common


class CommonTests(unittest.TestCase):
    def test_command_failure_is_error(self):
        with self.assertRaises(common.ProbeError):
            common.run([sys.executable, '-c', 'raise SystemExit(3)'])

    def test_command_timeout_is_error(self):
        with self.assertRaises(common.ProbeError):
            common.run([sys.executable, '-c', 'import time; time.sleep(2)'], timeout=0.05)

    def test_command_success_preserves_output(self):
        self.assertEqual(common.run([sys.executable, '-c', 'print("no")']), 'no\n')

    def test_duplicate_effective_setting_rejected(self):
        self.assertIsNone(common.setting('permitrootlogin no\npermitrootlogin yes', 'permitrootlogin'))
        self.assertEqual(common.setting('# x\nPermitRootLogin no', 'permitrootlogin'), 'no')

    def test_sudo_denial_accepts_explicit_zero_and_one(self):
        for code in (0,1):
            self.assertTrue(common.sudo_denied(code, 'User summit_employee is not allowed to run sudo on shop01.', 'summit_employee'))
        self.assertFalse(common.sudo_denied(1, 'sudo: unknown user', 'summit_employee'))
        self.assertFalse(common.sudo_denied(0, 'User nobody is not allowed to run sudo on shop01.', 'summit_employee'))
        self.assertFalse(common.sudo_denied(0, 'User summit_employee is not allowed to run sudo on shop01.\n(ALL) ALL', 'summit_employee'))

    def test_acl_named_write_is_unsafe_and_mask_is_applied(self):
        safe = 'user::rw-\ngroup::r--\nother::---\n'
        self.assertTrue(common.acl_safe(safe))
        self.assertFalse(common.acl_safe(safe + 'user:1001:rw-\nmask::rw-\n'))
        self.assertTrue(common.acl_safe(safe + 'user:1001:rw-\nmask::r--\n'))
        self.assertFalse(common.acl_safe(''))
        self.assertFalse(common.acl_safe(safe + 'default:user:1001:rwx\ndefault:mask::rwx\n'))

    def test_private_acl_rejects_named_readers(self):
        self.assertTrue(common.acl_safe('user::rw-\ngroup::---\nother::---\n', private=True))
        self.assertFalse(common.acl_safe('user::rw-\ngroup::---\nother::---\nuser:1001:r--\nmask::r--\n', private=True))

    def test_required_missing_file_is_not_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(common.protected(Path(temp)/'absent'))

if __name__ == '__main__': unittest.main()
