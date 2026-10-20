"""Pilot-only mutual-TLS gateway: exact POST /beacon, enrolled identity, no admin routes."""
import argparse
import base64
import hashlib
import http.client
import http.server
import json
import re
import ssl
import threading

LIMIT = 65536


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON member')
        result[key] = value
    return result


def route_allowed(method, path):
    return method == 'POST' and path == '/beacon'


def validate_beacon(blob, enrollment):
    if not blob or len(blob) > LIMIT:
        raise ValueError('Invalid beacon size')
    try:
        profile = json.loads(base64.b64decode(blob, validate=True), object_pairs_hook=unique_object)
    except Exception as error:
        raise ValueError('Invalid beacon encoding') from error
    if not isinstance(profile, dict):
        raise ValueError('Invalid profile')
    if profile.get('paw') != enrollment['paw'] or profile.get('host') != enrollment['host']:
        raise ValueError('Unenrolled identity')
    if (profile.get('executors') != ['summit-pilot']
            or enrollment.get('platform','linux') not in ('linux','windows')
            or profile.get('platform') != enrollment.get('platform','linux')):
        raise ValueError('Unexpected pilot capability')
    if profile.get('contact', 'http') != 'http' or profile.get('deadman_enabled', False):
        raise ValueError('Unsupported contact behavior')
    allowed = {'paw', 'host', 'group', 'platform', 'architecture', 'username', 'location', 'pid', 'ppid',
               'executors', 'privilege', 'exe_name', 'server', 'upstream_dest', 'contact', 'results',
               'deadman_enabled', 'available_contacts', 'host_ip_addrs'}
    if set(profile) - allowed:
        raise ValueError('Unexpected profile fields')
    results = profile.get('results', [])
    if not isinstance(results, list) or len(results) > 16:
        raise ValueError('Invalid result batch')
    for result in results:
        if not isinstance(result, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(result.get('id', ''))):
            raise ValueError('Invalid result ID')
        if set(result) - {'id', 'output', 'stderr', 'exit_code', 'pid', 'status'}:
            raise ValueError('Unexpected result fields')
        if result.get('status') not in (0, 1) or len(str(result.get('output', ''))) > 16384:
            raise ValueError('Invalid result status/output')
    profile.update(group='summit-pilot', trusted=True, contact='http', deadman_enabled=False,
                   available_contacts=['http'], server='https://10.77.70.20:8771',
                   upstream_dest='https://10.77.70.20:8771')
    return profile


class Gateway(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, config, context):
        self.config = config
        self.context = context
        self.slots = threading.BoundedSemaphore(16)
        self.issued = {}
        self.lock = threading.Lock()
        super().__init__(address, Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        # Handshake occurs in the bounded worker so a slow client cannot block accept().
        return self.context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False), address

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            request.do_handshake()
            super().process_request_thread(request, address)
        except (ssl.SSLError, OSError):
            request.close()
        finally:
            self.slots.release()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'SummitContact'

    def log_message(self, *args):
        pass

    def reply(self, code, body=b''):
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        self.reply(404)

    do_HEAD = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET
    do_OPTIONS = do_GET

    def do_POST(self):
        raw_target = self.requestline.split(' ')[1]
        if not route_allowed(self.command, raw_target):
            return self.reply(404)
        fingerprint = hashlib.sha256(self.connection.getpeercert(binary_form=True)).hexdigest()
        candidates = [value for value in self.server.config['enrollments'].values()
                      if value['cert_sha256'] == fingerprint and value['source'] == self.client_address[0]]
        if len(candidates) != 1:
            return self.reply(403)
        enrollment = candidates[0]
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isdigit():
            return self.reply(400)
        length = int(lengths[0])
        if not 0 < length <= LIMIT:
            return self.reply(413)
        try:
            profile = validate_beacon(self.rfile.read(length), enrollment)
            with self.server.lock:
                known = self.server.issued.setdefault(enrollment['paw'], {})
                if any(result['id'] not in known for result in profile.get('results', [])):
                    raise ValueError('Result was not issued to this guest by this gateway')
        except (ValueError, OSError):
            return self.reply(400)
        upstream = http.client.HTTPConnection('127.0.0.1', 8888, timeout=5)
        try:
            upstream.request('POST', '/beacon', body=base64.b64encode(json.dumps(profile).encode()),
                             headers={'Content-Type': 'text/plain'})
            response = upstream.getresponse()
            body = response.read(131073)
            if response.status != 200 or len(body) > 131072:
                return self.reply(502)
            decoded = json.loads(base64.b64decode(body, validate=True))
            if decoded.get('paw') != enrollment['paw']:
                return self.reply(502)
            instructions = json.loads(decoded.get('instructions', '[]'))
            if not isinstance(instructions, list) or len(instructions) > 16:
                return self.reply(502)
            with self.server.lock:
                known = self.server.issued[enrollment['paw']]
                for item in instructions:
                    item = json.loads(item) if isinstance(item, str) else item
                    known[item['id']] = True
                while len(known) > 256:
                    del known[next(iter(known))]
            return self.reply(200, body)
        except Exception:
            return self.reply(502)
        finally:
            upstream.close()


def make_server(config):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config['certificate'], config['key'])
    context.load_verify_locations(config['ca'])
    context.verify_mode = ssl.CERT_REQUIRED
    return Gateway((config['bind'], config['port']), config, context)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    with open(args.config) as file:
        config = json.load(file)
    with make_server(config) as server:
        server.serve_forever(poll_interval=0.25)
