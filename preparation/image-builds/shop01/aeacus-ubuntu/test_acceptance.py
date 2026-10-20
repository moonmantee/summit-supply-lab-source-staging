import unittest
import acceptance_helpers as h


class AcceptanceTests(unittest.TestCase):
    def test_proof_fingerprint_changes_when_runtime_scoring_changes(self):
        import tempfile
        from pathlib import Path
        fingerprint=getattr(h,'scenario_fingerprint',lambda root:{})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'probes').mkdir()
            for name in ('competition-manifest.json','build_config.py','ReadMe.conf'): (root/name).write_text('original')
            probe=root/'probes/check.py'; probe.write_text('original')
            before=fingerprint(root); probe.write_text('changed')
            self.assertNotEqual(before,fingerprint(root))
    def test_all_forty_required_even_with_correct_total(self):
        good={'count':40,'total_points':100,'expected_points':0,
              'checks':[{'id':i,'status':'FAIL'} for i in range(1,41)]}
        h.require_state(good, False)
        for change in ('missing','duplicate','error','points'):
            import copy
            bad=copy.deepcopy(good)
            if change=='missing': bad['checks'].pop()
            if change=='duplicate': bad['checks'][-1]['id']=1
            if change=='error': bad['checks'][0]['status']='ERROR'
            if change=='points': bad['expected_points']=2
            with self.assertRaises(ValueError): h.require_state(bad,False)

    def test_pam_preserves_domain_branches_and_rejects_unknown_flow(self):
        auth='auth [success=2 default=ignore] pam_unix.so nullok\nauth [success=1 default=ignore] pam_sss.so use_first_pass\nauth requisite pam_deny.so\nauth required pam_permit.so\n'
        password='password requisite pam_pwquality.so retry=3\npassword [success=2 default=ignore] pam_unix.so obscure use_authtok yescrypt\npassword sufficient pam_sss.so use_authtok\n'
        account='account sufficient pam_sss.so\naccount required pam_permit.so\n'
        a,c,p=h.secure_pam(auth,account,password)
        self.assertIn('pam_sss.so use_first_pass',a)
        self.assertIn('success=2 default=ignore] pam_sss',a)
        self.assertTrue(c.endswith(account))
        self.assertIn('local_users_only minlen=14 enforcing=1',p)
        self.assertIn('pam_pwhistory.so use_authtok remember=5',p)
        self.assertIn('password sufficient pam_sss.so use_authtok',p)
        with self.assertRaises(ValueError): h.secure_pam(auth.replace('success=2','success=9'),account,password)

    def test_apache_retains_php_tls_and_legitimate_logs(self):
        original='<VirtualHost *:80>\nRedirect / https://shop01/\n</VirtualHost>\n<VirtualHost *:443>\nSSLEngine on\nCustomLog /var/log/apache2/summit-access.log combined\nErrorLog /var/log/apache2/summit-error.log\nSetHandler application/x-httpd-php\n</VirtualHost>\n'
        text=h.secure_apache(original)
        self.assertIn('SetHandler application/x-httpd-php',text)
        self.assertIn('CustomLog /var/log/apache2/summit-access.log combined',text)
        self.assertIn('Options -Indexes',text)
        self.assertIn('Options -Includes',text)
        self.assertEqual(text.count('Require all denied'),3)
        with self.assertRaises(ValueError): h.secure_apache(original.replace('SSLEngine on','SSLEngine off'))


if __name__=='__main__': unittest.main()
