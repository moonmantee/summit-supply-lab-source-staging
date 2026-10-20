import copy
import unittest
import service_contract as s


class ContractTests(unittest.TestCase):
    def test_only_shop_catalog_expectations_change(self):
        original={'services':[{'id':'shop01-https','probe':'https','points':5,'sla_penalty':15,
                              'expected':list(s.OLD)}, {'id':'other','expected':['unchanged']}], 'event':'keep'}
        saved=copy.deepcopy(original)
        updated=s.correct(original)
        self.assertEqual(original,saved)
        self.assertEqual(updated['services'][0]['expected'],list(s.NEW))
        self.assertEqual(updated['services'][0]['points'],5)
        self.assertEqual(updated['services'][0]['sla_penalty'],15)
        self.assertEqual(updated['services'][1],original['services'][1])
        self.assertEqual(s.correct(updated),updated)
        bad=copy.deepcopy(original); bad['services'][0]['expected']=['unknown']
        with self.assertRaises(ValueError): s.correct(bad)


if __name__=='__main__': unittest.main()
