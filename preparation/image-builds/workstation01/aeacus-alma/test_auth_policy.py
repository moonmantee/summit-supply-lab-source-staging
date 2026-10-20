import unittest
from pathlib import Path
import tempfile

class PolicyTests(unittest.TestCase):
    def test_lockout_rehearsal_requires_real_valid_failure_records(self):
        from auth_policy import faillock_count
        text='summit-policy-test:\nWhen Type Source Valid\n2026-10-03 17:00:00 SVC login V\n2026-10-03 17:00:01 SVC login I\n2026-10-03 17:00:02 SVC login V\n'
        self.assertEqual(faillock_count(text,'summit-policy-test'),2)
        self.assertEqual(faillock_count('', 'summit-policy-test'),0)
        self.assertEqual(faillock_count('summit-policy-test:\nWhen Type Source Valid\n','summit-policy-test'),0)
        for bad in (text.replace('summit-policy-test:','other-user:'),text+'broken record\n',text.replace('login V','login X')):
            with self.assertRaises(ValueError): faillock_count(bad,'summit-policy-test')

    def test_pam_responses_do_not_confuse_current_and_new_passwords(self):
        from pam_runner import response_for
        self.assertEqual(response_for(1,'Current password:','user','change','old','new'),'old')
        self.assertEqual(response_for(1,'New password:','user','change','old','new'),'new')
        self.assertEqual(response_for(1,'Retype new password:','user','change','old','new'),'new')
        self.assertEqual(response_for(1,'Password:','user','authenticate','old',None),'old')
        self.assertEqual(response_for(2,'login:','user','authenticate','old',None),'user')
        self.assertIsNone(response_for(4,'Informational message','user','change','old','new'))
        with self.assertRaises(ValueError):
            response_for(1,'Unrecognized challenge:','user','change','old','new')

    def test_update_preserves_unrelated_settings_and_replaces_active_values(self):
        from auth_policy import update_policy
        text='# minlen = 2\nminlen = 8\nretry = 3\n'
        result=update_policy(text,{'minlen':'14','local_users_only':None})
        self.assertIn('# minlen = 2\n',result)
        self.assertIn('retry = 3\n',result)
        self.assertEqual([l for l in result.splitlines() if l.startswith('minlen')],['minlen = 14'])
        self.assertIn('local_users_only\n',result)

    def test_duplicate_active_values_are_rejected(self):
        from auth_policy import update_policy
        with self.assertRaises(ValueError):
            update_policy('deny = 3\ndeny = 5\n',{'deny':'0'})

if __name__=='__main__': unittest.main()
