import unittest
from competitor_access import pending_recovery_account


class CompetitorAccessTests(unittest.TestCase):
    def test_resume_only_matching_noninteractive_local_account(self):
        state={'local':True,'name':'competitor-recovery','uid':1007,'gid':1007,'group_name':'competitor-recovery','group_gid':1007,'home':'/home/competitor-recovery','home_uid':1007,'home_gid':1007,'home_mode':0o700,'home_symlink':False,'shell':'/sbin/nologin','grant_absent':True,'groups':['competitor-recovery']}
        self.assertTrue(pending_recovery_account(state))
        for change in ({'local':False},{'shell':'/bin/bash'},{'home_uid':0},{'home_symlink':True},{'grant_absent':False},{'groups':['competitor-recovery','wheel']},{'group_gid':1008}):
            self.assertFalse(pending_recovery_account(dict(state,**change)))
        self.assertFalse(pending_recovery_account({}))


if __name__=='__main__':
    unittest.main()
