import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch,Mock
import inject_services

BODY=b'{"site":"summit-warehouse","status":"ready","version":1}\n'

class ResourceTests(unittest.TestCase):
    def test_exact_http_fixture_and_wrong_content_redirect_failure(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                body=BODY if self.path=='/health.json' else b'wrong content'
                self.send_response(302 if self.path=='/redirect' else 200); self.end_headers(); self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        try:
            service={'probe':'http_resource','host':'127.0.0.1','scheme':'http','port':server.server_port,'path':'/health.json','sha256':hashlib.sha256(BODY).hexdigest()}
            self.assertEqual(inject_services.run_probe(service)[0],'PASS')
            self.assertEqual(inject_services.run_probe(dict(service,path='/wrong'))[0],'DOWN')
            self.assertEqual(inject_services.run_probe(dict(service,path='/redirect'))[0],'DOWN')
        finally: server.shutdown(); server.server_close(); worker.join()

    def test_https_requires_trust_and_validates_fixture(self):
        conn=Mock(); response=Mock(status=200); response.read1.side_effect=[BODY,b'']; conn.getresponse.return_value=response
        with patch('inject_services.ssl.create_default_context',return_value='verified-context') as tls, patch('inject_services.http.client.HTTPSConnection',return_value=conn) as https:
            service={'probe':'http_resource','host':'10.77.30.10','scheme':'https','port':443,'path':'/shipping-policy.txt','ca_file':'/private/shop.crt','sha256':hashlib.sha256(BODY).hexdigest()}
            self.assertEqual(inject_services.run_probe(service)[0],'PASS')
            tls.assert_called_once_with(cafile='/private/shop.crt')
            self.assertEqual(https.call_args.kwargs['context'],'verified-context')
            conn.close.assert_called_once()

    def test_invalid_ports_paths_hashes_and_insecure_https_rejected(self):
        valid={'probe':'http_resource','host':'10.77.20.10','scheme':'http','port':8080,'path':'/health.json','sha256':'a'*64}
        self.assertEqual(inject_services.validate(valid)['probe'],'http_resource')
        for extra in [{'port':True},{'port':0},{'path':'http://outside.test/'},{'sha256':'xyz'},{'scheme':'https'},{'scheme':'ftp'}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError): inject_services.validate(dict(valid,**extra))

if __name__=='__main__': unittest.main()
