import unittest
import tempfile
import threading
import time
from pathlib import Path
import web
from unittest.mock import patch

class WebTests(unittest.TestCase):
    def test_error_log_requires_a_fresh_context_request_token(self):
        observed=[]
        def request(path):
            observed.append(path)
            return (200,' '.join(web.MARKERS)+' order.php') if path.startswith('/?') else (403,'Forbidden')
        with patch.object(web,'active',return_value=True),patch.object(web,'fetch',side_effect=request),\
             patch.object(web,'read',return_value='ErrorLog /var/log/apache2/summit-error.log'),\
             patch.object(web.Path,'is_file',return_value=True),patch.object(web,'apache_open_log',return_value=True),\
             patch.object(web,'tail',return_value='old SUMMIT-ERROR-VALIDATION marker'),\
             patch.object(web,'wait_for_token',return_value=False):
            self.assertFalse(web.collect(37)['delivery_evidence'])
            self.assertTrue(any('SUMMIT-ERROR-VALIDATION/' in path for path in observed))
    def test_delayed_log_append_is_observed_within_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'access.log'; p.write_text('old request\n')
            def append():
                time.sleep(0.08)
                with p.open('a') as f: f.write('unique-request-token\n')
            worker=threading.Thread(target=append); worker.start()
            try: self.assertTrue(web.wait_for_token(p,'unique-request-token',timeout=0.5))
            finally: worker.join()

    def test_missing_log_token_times_out_without_credit(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'access.log'; p.write_text('old request\n')
            start=time.monotonic()
            self.assertFalse(web.wait_for_token(p,'absent-token',timeout=0.06))
            self.assertLess(time.monotonic()-start,0.5)

    def test_live_php_catalog_does_not_require_obsolete_static_marker(self):
        body='SUM-101 Ridgeline daypack SUM-102 Alpine insulated bottle SUM-103 Trail first aid kit order.php $50.00 $24.00 $18.00'
        self.assertTrue(web.healthy_catalog(body))
        self.assertFalse(web.healthy_catalog('Database error'))
        self.assertFalse(web.healthy_catalog(body.replace('SUM-102','MISSING')))

    def test_protected_url_requires_denial_not_server_failure(self):
        for status,want in [(403,True),(404,True),(200,False),(500,False),(0,False),(302,False)]:
            d={'running':True,'home_ok':True,'fixture_ready':True,'status':status,'body':'', 'fixture_retained':True}
            self.assertEqual(web.evaluate(32,d),want)

    def test_stopping_apache_or_destroying_fixture_cannot_pass(self):
        d={'running':True,'home_ok':True,'fixture_ready':True,'status':403,'body':'','fixture_retained':True}
        for key in ('running','home_ok','fixture_ready'):
            bad=dict(d); bad[key]=False; self.assertFalse(web.evaluate(33,bad))
        d['fixture_retained']=False; self.assertFalse(web.evaluate(30,d))

    def test_cgi_and_ssi_marker_execution_is_failure(self):
        base={'running':True,'home_ok':True,'fixture_ready':True,'fixture_retained':True}
        self.assertFalse(web.evaluate(34,{**base,'status':200,'body':'SUMMIT-CGI-EXECUTED'}))
        self.assertTrue(web.evaluate(34,{**base,'status':403,'body':''}))
        self.assertFalse(web.evaluate(35,{**base,'status':200,'body':'before\nSUMMIT-SSI-EXECUTED\nafter'}))
        self.assertTrue(web.evaluate(35,{**base,'status':200,'body':'<!--#include virtual="/marker.txt" -->'}))

    def test_logging_needs_active_config_and_delivery_evidence(self):
        good={'running':True,'home_ok':True,'configured':True,'file_exists':True,'delivery_evidence':True}
        self.assertTrue(web.evaluate(36,good))
        good['configured']=False; self.assertFalse(web.evaluate(36,good))

if __name__ == '__main__': unittest.main()
