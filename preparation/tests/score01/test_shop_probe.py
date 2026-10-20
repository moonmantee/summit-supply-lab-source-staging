"""Contract tests based on the supplied Summit PHP ordering routes."""
import importlib.util
from pathlib import Path
import unittest
import datetime as dt
import http.server
import ssl
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

import scorer

HOME = '''<article class="product">SUM-101 SUM-102 SUM-103</article>
<form method="post" action="/order.php"><input name="sku" value="SUM-101">
<input name="quantity" value="1"></form><a href="/order-history.php">History</a>'''


def rows(values, cls='result'):
    return '<div class="'+cls+'">'+''.join(
        '<div class="row"><span class="label">'+key+'</span><span>'+str(value)+'</span></div>'
        for key, value in values.items())+'</div>'


class Shop:
    def __init__(self, mode='working'):
        self.mode = mode
        self.orders = {}
        self.posts = []

    def __call__(self, path, data=None):
        if path == '/':
            return 200, HOME.encode()
        if path == '/order.php':
            if self.mode == 'order_404':
                return 404, b'missing'
            if self.mode == 'database_down':
                return 503, b'Order service temporarily unavailable.'
            if data['sku'].startswith('SCORER-MISSING-') and self.mode != 'static_order':
                return 404, b'Product not found.'
            self.posts.append(data)
            token = 'WEB-20261019-143000-ABC123'
            if self.mode == 'confirmation_only':
                return 200, token.encode()
            order = {'Order ID': '42', 'Order token': token, 'SKU': data['sku'],
                     'Quantity': data['quantity'], 'Status': 'submitted'}
            self.orders[token] = order
            return 200, rows({k: v for k, v in order.items() if k != 'Status'}, 'product').encode()
        query = parse_qs(urlsplit(path).query)
        token = query['token'][0]
        if self.mode == 'history_404':
            return 404, b'missing'
        if self.mode == 'static_history':
            return 200, rows({'Order ID': '42', 'Order token': 'WEB-20261019-143000-ABC123',
                              'SKU': 'SUM-101', 'Quantity': '1', 'Status': 'submitted'}).encode()
        if self.mode == 'static_echo':
            return 200, ('<input value="'+token+'">No order was found with that token.').encode()
        if token not in self.orders:
            return 200, ('<input value="'+token+'"><div class="error">No order was found with that token.</div>').encode()
        order = dict(self.orders[token])
        if self.mode == 'wrong_quantity':
            order['Quantity'] = '99'
        if self.mode == 'wrong_sku':
            order['SKU'] = 'WRONG'
        if self.mode == 'wrong_id':
            order['Order ID'] = '900'
        if self.mode == 'not_submitted':
            order['Status'] = 'cancelled'
        if self.mode == 'no_history_result':
            return 200, ('<input value="'+token+'">').encode()
        if self.mode == 'confirmation_as_history':
            return 200, rows(order, 'product').encode()
        return 200, rows(order).encode()


class ShopProbeTests(unittest.TestCase):
    def setUp(self):
        import shop_probe
        self.module = shop_probe
        self.config = {'probe': 'https', 'url': 'https://10.77.30.10/',
                       'expected': ['SUM-101', 'SUM-102', 'SUM-103']}

    def test_working_order_and_history_pass(self):
        shop = Shop()
        status, reason = self.module.probe(self.config, fetch=shop)
        self.assertEqual(status, 'PASS', reason)
        self.assertEqual(len(shop.posts), 1)
        self.assertIn(shop.posts[0]['sku'], ('SUM-101', 'SUM-102', 'SUM-103'))
        self.assertIn(int(shop.posts[0]['quantity']), range(1, 6))

    def test_broken_and_frozen_application_responses_fail(self):
        for mode in ['order_404', 'database_down', 'history_404', 'static_history', 'static_order',
                     'static_echo', 'wrong_quantity', 'wrong_sku', 'wrong_id',
                     'not_submitted', 'no_history_result', 'confirmation_only',
                     'confirmation_as_history']:
            with self.subTest(mode=mode):
                self.assertEqual(self.module.probe(self.config, fetch=Shop(mode))[0], 'DOWN')

    def test_frozen_home_with_no_order_form_fails_before_post(self):
        def fetch(path, data=None):
            self.assertIsNone(data)
            return 200, b'SUM-101 SUM-102 SUM-103'
        self.assertEqual(self.module.probe(self.config, fetch=fetch)[0], 'DOWN')

    def test_missing_catalog_marker_fails(self):
        config = dict(self.config, expected=['missing'])
        shop = Shop()
        self.assertEqual(self.module.probe(config, fetch=shop)[0], 'DOWN')
        self.assertFalse(shop.posts)

    def test_redirect_is_down(self):
        self.assertEqual(self.module.probe(self.config, fetch=lambda *args: (302, b''))[0], 'DOWN')

    def test_invalid_tls_and_origin_configuration_is_invalid(self):
        for config in [dict(self.config, verify_tls=False),
                       dict(self.config, url='http://10.77.30.10/'),
                       dict(self.config, expected='SUM-101')]:
            self.assertEqual(self.module.probe(config, fetch=Shop())[0], 'INVALID')

    def test_network_failure_is_down(self):
        def fetch(*args):
            raise TimeoutError('fixture timeout')
        self.assertEqual(self.module.probe(self.config, fetch=fetch)[0], 'DOWN')

    def test_both_scorer_copies_dispatch_shop_check(self):
        from unittest.mock import patch
        for path in [Path(__file__).with_name('scorer.py'),
                     Path(__file__).parent/'team-portal-package/scorer.py']:
            spec = importlib.util.spec_from_file_location('scorer_candidate', path)
            candidate = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(candidate)
            with patch('shop_probe.probe', return_value=('DOWN', 'static fixture rejected')) as probe:
                result = candidate.run_probe(dict(self.config, id='shop01-https'))
            self.assertEqual(result[0], 'DOWN')
            probe.assert_called_once()


class HTTPSShopTests(unittest.TestCase):
    """Exercise real TLS, URL-encoded POSTs, and query-token lookup."""
    @classmethod
    def setUpClass(cls):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        cls.temp = tempfile.TemporaryDirectory()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'shop.test')])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-dt.timedelta(minutes=1)).not_valid_after(now+dt.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('shop.test')]), False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
                .sign(key, hashes.SHA256()))
        cls.cert = Path(cls.temp.name)/'cert.pem'
        cls.cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        keypath = Path(cls.temp.name)/'key.pem'
        keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, keypath)
        cls.shop = Shop()

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                code, body = cls.shop(self.path)
                self.respond(code, body)

            def do_POST(self):
                data = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
                code, body = cls.shop(self.path, {k: v[0] for k, v in data.items()})
                self.respond(code, body)

            def respond(self, code, body):
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def config(self):
        return {'id': 'shop01-https', 'probe': 'https',
                'url': f'https://shop.test:{self.server.server_port}/',
                'connect_host': '127.0.0.1', 'ca_file': str(self.cert),
                'expected': ['SUM-101', 'SUM-102', 'SUM-103']}

    def test_real_tls_post_and_history(self):
        self.shop.mode = 'working'
        status, reason = scorer.run_probe(self.config())
        self.assertEqual(status, 'PASS', reason)

    def test_real_tls_static_history_rejected(self):
        self.shop.mode = 'static_history'
        self.assertEqual(scorer.run_probe(self.config())[0], 'DOWN')

    def test_untrusted_certificate_rejected(self):
        config = self.config()
        del config['ca_file']
        self.assertEqual(scorer.run_probe(config)[0], 'DOWN')

    def test_wrong_certificate_identity_rejected(self):
        config = self.config()
        config['url'] = f'https://127.0.0.1:{self.server.server_port}/'
        self.assertEqual(scorer.run_probe(config)[0], 'DOWN')


if __name__ == '__main__':
    unittest.main()
