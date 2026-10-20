"""Summit HTTPS order transaction probe; no database credentials required."""
import http.client
from html.parser import HTMLParser
import ipaddress
import re
import secrets
import ssl
from urllib.parse import urlencode, urlsplit

MAX_BODY = 1024 * 1024
SKUS = ('SUM-101', 'SUM-102', 'SUM-103')
TOKEN = re.compile(r'WEB-\d{8}-\d{6}-[A-F0-9]{6}')


class Down(Exception):
    pass


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return ' '.join(' '.join(c.text() if isinstance(c, Node) else c
                               for c in self.children).split())

    def find(self, tag=None, cls=None):
        for child in self.children:
            if isinstance(child, Node):
                if ((tag is None or child.tag == tag) and
                        (cls is None or cls in child.attrs.get('class', '').split())):
                    yield child
                yield from child.find(tag, cls)


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(body.decode('utf-8', errors='replace'))

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack[-1].tag not in {'script', 'style'}:
            self.stack[-1].children.append(data)


def fields(node):
    result = {}
    for row in node.find(cls='row'):
        cells = [c for c in row.children if isinstance(c, Node)]
        if len(cells) == 2:
            key, value = (c.text() for c in cells)
            if key in result:
                raise Down('Order response contains ambiguous fields')
            result[key] = value
    return result


def transport(config):
    parsed = urlsplit(config['url'])
    context = ssl.create_default_context(cafile=config.get('ca_file'))
    connect_host = config.get('connect_host')
    if connect_host is not None:
        connect_host = str(ipaddress.ip_address(connect_host))

    class Connection(http.client.HTTPSConnection):
        def connect(self):
            # Preserve TLS SNI and certificate identity when routing to an explicit IP.
            original = self.host
            try:
                if connect_host:
                    self.host = connect_host
                http.client.HTTPConnection.connect(self)
            finally:
                self.host = original
            try:
                self.sock = context.wrap_socket(self.sock, server_hostname=original)
            except BaseException:
                self.sock.close()
                raise

    def fetch(path, data=None):
        body = urlencode(data).encode('ascii') if data is not None else None
        headers = {'User-Agent': 'Summit-CCDC-Scorer/3.0', 'Cache-Control': 'no-cache, no-store'}
        if body is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        connection = Connection(parsed.hostname, parsed.port or 443,
                                timeout=float(config.get('timeout', 6)), context=context)
        try:
            connection.request('POST' if data is not None else 'GET', path, body, headers)
            response = connection.getresponse()
            content = response.read(MAX_BODY+1)
            if len(content) > MAX_BODY:
                raise Down('Shop response exceeds the permitted size')
            return response.status, content
        finally:
            connection.close()
    return fetch


def probe(config, *, fetch=None):
    try:
        parsed = urlsplit(config.get('url', ''))
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            return 'INVALID', 'Shop probe requires an HTTPS root URL without credentials'
        if config.get('verify_tls', True) is not True:
            return 'INVALID', 'Shop probe requires trusted TLS'
        expected = config.get('expected', [])
        if not isinstance(expected, list) or not all(isinstance(x, str) and x for x in expected):
            return 'INVALID', 'Shop catalog expectations must be a list of nonempty strings'
        if fetch is None:
            try:
                fetch = transport(config)
            except (OSError, ValueError, ssl.SSLError):
                return 'INVALID', 'Shop TLS trust or connection configuration is invalid'

        def page(path, data=None, status=200):
            code, body = fetch(path, data)
            if code != status:
                raise Down(f'Shop {path.split("?")[0]} returned HTTP {code}; expected {status}')
            if len(body) > MAX_BODY:
                raise Down('Shop response exceeds the permitted size')
            return Document(body).root

        home = page('/')
        if any(marker not in home.text() for marker in expected):
            raise Down('Expected catalog content is missing or changed')
        forms = [f for f in home.find('form') if f.attrs.get('method', 'get').lower() == 'post'
                 and f.attrs.get('action') in ('order.php', '/order.php')]
        if not any({'sku', 'quantity'} <= {n.attrs.get('name') for n in f.find()
                                         if n.tag in {'input', 'select'}} for f in forms):
            raise Down('Catalog order form is missing')

        # A static confirmation cannot correctly reject a random nonexistent SKU.
        page('/order.php', {'sku': 'SCORER-MISSING-'+secrets.token_hex(16), 'quantity': '1'}, 404)
        missing = 'WEB-00000000-000000-'+secrets.token_hex(16).upper()
        absent = page('/order-history.php?'+urlencode({'token': missing}))
        if (list(absent.find(cls='result')) or
                not any('No order was found with that token.' in n.text()
                        for n in absent.find(cls='error'))):
            raise Down('Order history did not reject a nonexistent order token')

        sku, quantity = secrets.choice(SKUS), str(secrets.randbelow(5)+1)
        receipt = fields(page('/order.php', {'sku': sku, 'quantity': quantity}))
        token, order_id = receipt.get('Order token', ''), receipt.get('Order ID', '')
        if (not TOKEN.fullmatch(token) or not order_id.isascii() or not order_id.isdigit()
                or int(order_id) < 1 or receipt.get('SKU') != sku
                or receipt.get('Quantity') != quantity):
            raise Down('Order confirmation did not match the submitted order')
        history = page('/order-history.php?'+urlencode({'token': token}))
        results = list(history.find(cls='result'))
        if len(results) != 1:
            raise Down('Order history result is missing or ambiguous')
        stored = fields(results[0])
        wanted = {'Order ID': order_id, 'Order token': token, 'SKU': sku,
                  'Quantity': quantity, 'Status': 'submitted'}
        if any(stored.get(k) != v for k, v in wanted.items()):
            raise Down('Order history does not match the newly submitted order')
        return 'PASS', 'Trusted HTTPS catalog, order submission and matching order history verified'
    except Down as error:
        return 'DOWN', str(error)
    except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException, UnicodeError):
        return 'DOWN', 'Shop HTTPS connection or ordering transaction failed'


if __name__ == '__main__':
    import json
    from pathlib import Path
    import sys
    config = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else 'config.json').read_text())
    service, = [s for s in config['services'] if s.get('id') == 'shop01-https']
    result = probe(service)
    print(': '.join(result))
    raise SystemExit(0 if result[0] == 'PASS' else 1)
