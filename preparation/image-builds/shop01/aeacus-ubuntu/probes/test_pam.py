import unittest
import pam

class PamTests(unittest.TestCase):
    def test_lockout_rejects_bypass_controls_and_service_entry_bypass(self):
        auth=('auth [success=ok default=1] pam_localuser.so\nauth required pam_faillock.so preauth\n'
              'auth [success=3 default=ignore] pam_unix.so nullok\nauth [success=2 default=ignore] pam_sss.so use_first_pass\n'
              'auth [default=die] pam_faillock.so authfail\nauth requisite pam_deny.so\n'
              'auth required pam_faillock.so authsucc\nauth required pam_permit.so\n')
        d={'auth':auth,'account':'account required pam_faillock.so\naccount required pam_unix.so',
           'faillock':{'deny':'5','fail_interval':'900','unlock_time':'900','local_users_only':True}}
        self.assertTrue(pam.evaluate(9,d))
        for changed in ('auth sufficient pam_permit.so\n'+auth,auth.replace('success=3','success=5'),
                        auth.replace('required pam_faillock.so authsucc','optional pam_faillock.so authsucc')):
            bad=dict(d,auth=changed); self.assertFalse(pam.evaluate(9,bad))
        bad=dict(d,services=[dict(d,auth='auth sufficient pam_permit.so\n'+auth)])
        self.assertFalse(pam.evaluate(9,bad))
    def fixture(self):
        return {'password':'password requisite pam_pwquality.so retry=3 local_users_only\npassword [success=2 default=ignore] pam_unix.so use_authtok yescrypt\npassword sufficient pam_sss.so use_authtok',
                'quality':{'minlen':'14','enforcing':'1','dcredit':'0','ucredit':'0','lcredit':'0','ocredit':'0'}}

    def test_module_arguments_override_config(self):
        d=self.fixture(); self.assertTrue(pam.evaluate(7,d))
        d['password']=d['password'].replace('retry=3','retry=3 minlen=6')
        self.assertFalse(pam.evaluate(7,d))

    def test_positive_credit_cannot_shorten_fourteen_character_minimum(self):
        d=self.fixture(); d['quality']['dcredit']='2'
        self.assertFalse(pam.evaluate(7,d))

    def test_comment_or_optional_quality_module_is_not_enforcement(self):
        d=self.fixture(); self.assertTrue(pam.evaluate(8,d))
        for replacement in ('# password requisite','password optional','password sufficient'):
            d=self.fixture(); d['password']=d['password'].replace('password requisite',replacement)
            self.assertFalse(pam.evaluate(8,d))
        d=self.fixture(); d['quality']['enforcing']='0'
        self.assertFalse(pam.evaluate(8,d))

    def test_history_requires_local_guard_and_precedes_password_write(self):
        d=self.fixture(); d['history']={'remember':'5'}
        d['password']=d['password'].replace('password [success=2',
            'password [success=ok default=1] pam_localuser.so\npassword required pam_pwhistory.so use_authtok\npassword [success=2')
        self.assertTrue(pam.evaluate(10,d))
        d['password']=d['password'].replace('password required pam_pwhistory.so','password optional pam_pwhistory.so')
        self.assertFalse(pam.evaluate(10,d))

    def test_lockout_settings_alone_do_not_integrate_authentication(self):
        d={'faillock':{'deny':'5','fail_interval':'900','unlock_time':'900','local_users_only':True},
           'auth':'auth required pam_unix.so','account':'account required pam_unix.so'}
        self.assertFalse(pam.evaluate(9,d))

    def test_policy_last_value_wins_and_comments_are_ignored(self):
        self.assertEqual(pam.policy('minlen=14\n# minlen=1\nminlen = 6\nlocal_users_only\n'), {'minlen':'6','local_users_only':True})

if __name__ == '__main__': unittest.main()
