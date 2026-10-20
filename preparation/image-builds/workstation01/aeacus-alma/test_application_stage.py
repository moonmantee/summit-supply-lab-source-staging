import unittest
from application_stage import firefox_state,dnf_state


class ApplicationStageTests(unittest.TestCase):
    def test_browser_preserves_unrelated_policy_and_input(self):
        data={'policies':{'Homepage':{'URL':'https://portal.corp.summit.test'},'Preferences':{'unrelated':{'Value':42}}}}
        planted=firefox_state(data,False)
        self.assertEqual(planted['policies']['Homepage'],data['policies']['Homepage'])
        self.assertEqual(planted['policies']['Preferences']['unrelated'],{'Value':42})
        self.assertNotIn('browser.safebrowsing.downloads.enabled',data['policies']['Preferences'])
        self.assertFalse(planted['policies']['Preferences']['browser.safebrowsing.downloads.enabled']['Value'])
        self.assertTrue(firefox_state(planted,True)['policies']['Preferences']['browser.safebrowsing.downloads.enabled']['Value'])

    def test_update_exclusions_preserve_other_settings_and_other_sections(self):
        text='[main]\ngpgcheck=1\nexclude=kernel*\n# retain this comment\n[other]\nexclude=other*\n'
        result=dnf_state(text,True)
        self.assertIn('exclude=kernel* firefox gedit',result)
        self.assertIn('# retain this comment',result)
        self.assertIn('[other]\nexclude=other*',result)
        self.assertEqual(dnf_state(text,False),text)

    def test_absent_exclusion_added_only_to_main(self):
        result=dnf_state('[main]\ngpgcheck=1\n[other]\nexclude=other*\n',True)
        self.assertIn('[main]\nexclude=firefox gedit\n',result)
        self.assertIn('[other]\nexclude=other*',result)

    def test_malformed_configuration_aborts(self):
        with self.assertRaises(ValueError):
            firefox_state({'policies':[]},False)
        with self.assertRaises(ValueError):
            dnf_state('[main]\nexclude=a\nexclude=b\n',True)


if __name__=='__main__':
    unittest.main()
