import unittest
from policy import browser_protected, update_allowed, path_protected, cockpit_absent


class PolicyTests(unittest.TestCase):
    def test_browser_requires_locked_true_not_false_or_missing(self):
        p={'policies': {'Preferences': {'browser.safebrowsing.downloads.enabled': {'Value': True, 'Status': 'locked'}}}}
        self.assertTrue(browser_protected(p, ['browser.safebrowsing.downloads.enabled']))
        p['policies']['Preferences']['browser.safebrowsing.downloads.enabled']['Value']=False
        self.assertFalse(browser_protected(p, ['browser.safebrowsing.downloads.enabled']))
        self.assertFalse(browser_protected({}, ['browser.safebrowsing.downloads.enabled']))

    def test_phishing_and_malware_both_required(self):
        p={'policies': {'Preferences': {'a': {'Value': True, 'Status': 'locked'}}}}
        self.assertFalse(browser_protected(p, ['a','b']))

    def test_malformed_browser_policy_fails_closed(self):
        for p in ({'policies': []}, {'policies': {'Preferences': []}}, None):
            self.assertFalse(browser_protected(p, ['a']))

    def test_update_wildcards_and_disabled_repositories(self):
        self.assertTrue(update_allowed('firefox', {'/etc/dnf/dnf.conf': '[main]\nexclude=gedit\n'}))
        self.assertFalse(update_allowed('firefox', {'/etc/dnf/dnf.conf': '[main]\nexclude=fire*\n'}))
        self.assertTrue(update_allowed('firefox', {'/etc/dnf/dnf.conf': '[main]\n', 'x.repo': '[x]\nenabled=0\nexclude=*\n'}))
        self.assertFalse(update_allowed('firefox', {'/etc/dnf/dnf.conf': '[main]\n', 'x.repo': '[x]\nexcludepkgs=firefox*\n'}))

    def test_includepkgs_and_malformed_files_fail_closed(self):
        self.assertFalse(update_allowed('firefox', {'/etc/dnf/dnf.conf': '[main]\n', 'x.repo': '[x]\nincludepkgs=gedit\n'}))
        self.assertFalse(update_allowed('firefox', {'/etc/dnf/dnf.conf': 'bad syntax'}))
        self.assertFalse(update_allowed('firefox', {}))

    def test_secure_file_requires_all_parent_permissions_and_acl_check(self):
        p=[{'uid':0,'mode':0o755,'kind':'directory'}, {'uid':0,'mode':0o644,'kind':'file'}]
        self.assertTrue(path_protected(p, True))
        self.assertFalse(path_protected(p, False))
        self.assertFalse(path_protected([dict(p[0],mode=0o777),p[1]],True))
        self.assertFalse(path_protected([p[0],dict(p[1],uid=1000)],True))
        self.assertFalse(path_protected([],True))

    def test_cockpit_removed_vs_package_query_error(self):
        self.assertTrue(cockpit_absent(1, 'package cockpit-ws is not installed\n'))
        self.assertFalse(cockpit_absent(0, 'cockpit-ws-356.2\n'))
        self.assertFalse(cockpit_absent(1, 'rpm database error\n'))


if __name__ == '__main__':
    unittest.main()
