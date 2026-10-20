import unittest
import persistence

class PersistenceTests(unittest.TestCase):
    def test_running_disabled_service_is_not_removed(self):
        self.assertFalse(persistence.evaluate(39, {'references_absent':True,'unit':{'LoadState':'loaded','ActiveState':'active','UnitFileState':'disabled'}}))
        self.assertTrue(persistence.evaluate(39, {'references_absent':True,'unit':{'LoadState':'not-found','ActiveState':'inactive','UnitFileState':''}}))
        self.assertFalse(persistence.evaluate(39, {'references_absent':False,'unit':{'LoadState':'not-found','ActiveState':'inactive'}}))

    def test_suid_removal_is_independent_of_executable_retention(self):
        self.assertTrue(persistence.evaluate(40, {'present':False}))
        self.assertTrue(persistence.evaluate(40, {'present':True,'mode':0o755}))
        self.assertFalse(persistence.evaluate(40, {'present':True,'mode':0o4755}))

if __name__ == '__main__': unittest.main()
