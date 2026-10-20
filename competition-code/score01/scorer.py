"""Config-driven CCDC-style availability and SLA scorer."""
import concurrent.futures
from contextlib import closing
import datetime as dt
import http.client
import ipaddress
import json
from pathlib import Path
import random
import socket
import sqlite3
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = Path(__file__).resolve().parent
MAX_BODY = 1024 * 1024
FAILURES_PER_SLA = 5
VALID_STATUSES = {'PASS', 'DOWN', 'INVALID'}


class ConfigurationError(ValueError):
    """A local scorer configuration error, never contestant downtime."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DirectHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an explicit IP while retaining the URL's TLS/HTTP identity."""
    def __init__(self, host, *, connect_host, **kwargs):
        self.connect_host = connect_host
        super().__init__(host, **kwargs)

    def connect(self):
        if self._tunnel_host:
            raise ConfigurationError('Direct HTTPS does not support proxy tunnels')
        raw = socket.create_connection((self.connect_host, self.port), self.timeout,
                                       source_address=self.source_address)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _required(config, name, expected_type=None):
    if name not in config:
        raise ConfigurationError(f'missing {name}')
    value = config[name]
    if expected_type is not None and not isinstance(value, expected_type):
        raise ConfigurationError(f'{name} has the wrong type')
    return value


def validate_page(status, body, expected):
    if status != 200:
        return 'DOWN', 'Website returned HTTP ' + str(status)
    if len(body) > MAX_BODY:
        return 'DOWN', 'Website response exceeds the permitted size'
    text = body.decode('utf-8', errors='replace')
    missing = [marker for marker in expected if marker not in text]
    if missing:
        return 'DOWN', 'Expected website content is missing or changed'
    return 'PASS', 'Expected website content verified'


def _ssl_context(config):
    verify = config.get('verify_tls', True)
    if not isinstance(verify, bool):
        raise ConfigurationError('verify_tls must be true or false')
    if not verify:
        return ssl._create_unverified_context()
    ca_file = config.get('ca_file')
    try:
        return ssl.create_default_context(cafile=ca_file)
    except (OSError, ssl.SSLError) as error:
        raise ConfigurationError('TLS trust file cannot be loaded') from error


def _http_probe(config):
    url = _required(config, 'url', str)
    parsed = urllib.parse.urlsplit(url)
    expected_scheme = 'https' if config['probe'] == 'https' else 'http'
    if parsed.scheme != expected_scheme or not parsed.hostname:
        raise ConfigurationError(f'{expected_scheme.upper()} URL is required')
    expected = config.get('expected', [])
    if not isinstance(expected, list) or not all(isinstance(item, str) and item for item in expected):
        raise ConfigurationError('expected must be a list of nonempty strings')
    statuses = config.get('expected_status', [200])
    if not isinstance(statuses, list) or not statuses or not all(isinstance(item, int) for item in statuses):
        raise ConfigurationError('expected_status must be a nonempty integer list')
    timeout = float(config.get('timeout', 6))
    handlers = [urllib.request.ProxyHandler({})]
    if parsed.scheme == 'https':
        context = _ssl_context(config)
        connect_host = config.get('connect_host')
        if connect_host is not None:
            try:
                connect_host = str(ipaddress.ip_address(connect_host))
            except (ValueError, TypeError) as error:
                raise ConfigurationError('connect_host must be an IP address') from error
            class DirectHandler(urllib.request.HTTPSHandler):
                def https_open(self, request):
                    return self.do_open(lambda host, **kwargs: DirectHTTPSConnection(
                        host, connect_host=connect_host, **kwargs), request, context=context)
            handlers.append(DirectHandler(context=context))
        else:
            handlers.append(urllib.request.HTTPSHandler(context=context))
    if not config.get('follow_redirects', False):
        handlers.append(NoRedirect())
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={'User-Agent': 'Summit-CCDC-Scorer/2.0', 'Cache-Control': 'no-cache'})
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BODY + 1)
            if response.status not in statuses:
                return 'DOWN', f'Website returned HTTP {response.status}'
            if len(body) > MAX_BODY:
                return 'DOWN', 'Website response exceeds the permitted size'
            if expected:
                state, reason = validate_page(response.status, body, expected)
                if state != 'PASS':
                    return state, reason
            return 'PASS', f'{parsed.scheme.upper()} response and expected content verified'
    except urllib.error.HTTPError as error:
        origin=config.get('redirect_origin')
        if origin and error.code in {301,302,307,308} and error.headers.get('Location')==origin:
            return 'PASS','HTTP redirect to the required HTTPS origin verified'
        return 'DOWN', 'Website returned HTTP ' + str(error.code)
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError):
        return 'DOWN', f'{parsed.scheme.upper()} connection, TLS, or response failed'


def _connect(config):
    host = _required(config, 'host', str)
    port = _required(config, 'port', int)
    if not 1 <= port <= 65535:
        raise ConfigurationError('port is outside 1-65535')
    return socket.create_connection((host, port), timeout=float(config.get('timeout', 5)))


def _banner_probe(config):
    expected = _required(config, 'banner_prefix', str).encode('ascii')
    with _connect(config) as connection:
        connection.settimeout(float(config.get('timeout', 5)))
        banner = connection.recv(512)
    if not banner.startswith(expected):
        return 'DOWN', 'Service returned an unexpected protocol banner'
    return 'PASS', f'{config.get("label", "Service")} protocol banner verified'


def _smtp_probe(config):
    with _connect(config) as connection:
        connection.settimeout(float(config.get('timeout', 5)))
        stream = connection.makefile('rwb', buffering=0)
        banner = stream.readline(1024)
        if not banner.startswith(b'220'):
            return 'DOWN', 'SMTP greeting was not accepted'
        stream.write(b'EHLO score01.infra.test\r\n')
        lines = []
        for _ in range(20):
            line = stream.readline(2048)
            if not line:
                break
            lines.append(line)
            if len(line) >= 4 and line[:3] == b'250' and line[3:4] != b'-':
                break
        try:
            stream.write(b'QUIT\r\n')
        except OSError:
            pass
    if not lines or not lines[-1].startswith(b'250'):
        return 'DOWN', 'SMTP EHLO transaction failed'
    return 'PASS', 'SMTP greeting and EHLO transaction verified'


def _imaps_probe(config):
    host = _required(config, 'host', str)
    context = _ssl_context(config)
    with _connect(config) as connection:
        with context.wrap_socket(connection, server_hostname=host) as secured:
            secured.settimeout(float(config.get('timeout', 5)))
            greeting = secured.recv(2048)
    if not greeting.upper().startswith(b'* OK'):
        return 'DOWN', 'IMAPS TLS succeeded but the IMAP greeting was invalid'
    return 'PASS', 'IMAPS TLS handshake and IMAP greeting verified'


def _dns_name(name):
    labels = name.rstrip('.').split('.')
    if not labels or any(not label or len(label.encode('idna')) > 63 for label in labels):
        raise ConfigurationError('invalid DNS query name')
    return b''.join(bytes([len(label.encode('idna'))]) + label.encode('idna') for label in labels) + b'\0'


def _skip_dns_name(packet, offset):
    for _ in range(128):
        if offset >= len(packet):
            raise OSError('truncated DNS name')
        length = packet[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise OSError('truncated DNS pointer')
            return offset + 2
        offset += 1 + length
    raise OSError('invalid DNS name')


def _dns_probe(config):
    server = _required(config, 'server', str)
    name = _required(config, 'query', str)
    expected = _required(config, 'expected_address', str)
    try:
        socket.inet_aton(expected)
    except OSError as error:
        raise ConfigurationError('expected_address is not IPv4') from error
    request_id = random.SystemRandom().randrange(0, 65536)
    question = _dns_name(name) + struct.pack('!HH', 1, 1)
    request = struct.pack('!HHHHHH', request_id, 0x0100, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(float(config.get('timeout', 5)))
        client.sendto(request, (server, 53))
        response, _ = client.recvfrom(4096)
    if len(response) < 12:
        return 'DOWN', 'DNS response was truncated'
    response_id, flags, questions, answers, _, _ = struct.unpack('!HHHHHH', response[:12])
    if response_id != request_id or flags & 0x000F:
        return 'DOWN', 'DNS server returned an invalid response'
    offset = 12
    for _ in range(questions):
        offset = _skip_dns_name(response, offset) + 4
    addresses = []
    for _ in range(answers):
        offset = _skip_dns_name(response, offset)
        if offset + 10 > len(response):
            raise OSError('truncated DNS answer')
        record_type, record_class, _, length = struct.unpack('!HHIH', response[offset:offset + 10])
        offset += 10
        data = response[offset:offset + length]
        offset += length
        if record_type == 1 and record_class == 1 and length == 4:
            addresses.append(socket.inet_ntoa(data))
    if expected not in addresses:
        return 'DOWN', f'DNS did not return expected address {expected}'
    return 'PASS', f'DNS resolved {name} to {expected}'


PROBES = {'http': _http_probe, 'https': _http_probe, 'banner': _banner_probe,
          'smtp': _smtp_probe, 'imaps': _imaps_probe, 'dns': _dns_probe}


def run_probe(config):
    try:
        # Summit order/history transaction check.
        if config.get('id') == 'shop01-https' and config.get('probe') == 'https':
            from shop_probe import probe as shop_probe
            return shop_probe(config)
        probe_name = _required(config, 'probe', str)
        if probe_name in {'dns_record','ftp_share','https_upgrade','mail_alias','http_resource'}:
            from inject_services import run_probe as inject_probe
            return inject_probe(config)
        probe = PROBES.get(probe_name)
        if probe is None:
            raise ConfigurationError('unknown probe type')
        return probe(config)
    except ConfigurationError as error:
        return 'INVALID', f'Scorer configuration error: {error}'
    except (OSError, TimeoutError, ssl.SSLError, UnicodeError):
        return 'DOWN', 'Service connection or protocol transaction failed'
    except Exception as error:
        return 'INVALID', f'Scorer internal error: {type(error).__name__}'


def check(config):
    """Backward-compatible single HTTPS check used by prior tooling."""
    legacy = dict(config)
    legacy.setdefault('probe', 'https')
    legacy.setdefault('verify_tls', True)
    return run_probe(legacy)


def initialize_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS scoring_rounds (
        id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
        points_awarded INTEGER NOT NULL DEFAULT 0,
        sla_deductions INTEGER NOT NULL DEFAULT 0,
        net_points INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE IF NOT EXISTS service_checks (
        id INTEGER PRIMARY KEY, round_id INTEGER NOT NULL, timestamp TEXT NOT NULL,
        service_id TEXT NOT NULL, host_name TEXT NOT NULL, service_name TEXT NOT NULL,
        status TEXT NOT NULL, reason TEXT NOT NULL, latency_ms INTEGER NOT NULL,
        awarded_points INTEGER NOT NULL, sla_deduction INTEGER NOT NULL,
        consecutive_failures INTEGER NOT NULL,
        FOREIGN KEY(round_id) REFERENCES scoring_rounds(id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS service_state (
        service_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0,
        total_points INTEGER NOT NULL DEFAULT 0,
        total_sla_deductions INTEGER NOT NULL DEFAULT 0,
        last_status TEXT, last_timestamp TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS service_checks_round_idx ON service_checks(round_id)')
    db.execute('CREATE INDEX IF NOT EXISTS service_checks_service_idx ON service_checks(service_id,id)')


def get_failure_count(db, service_id, event_id=None):
    if event_id is None:
        row = db.execute(
            'SELECT consecutive_failures FROM service_state WHERE service_id=?',
            (service_id,),
        ).fetchone()
    else:
        row = db.execute(
            'SELECT consecutive_failures FROM event_service_state WHERE event_id=? AND service_id=?',
            (event_id, service_id),
        ).fetchone()
    return row[0] if row else 0


def apply_scoring_result(db, service, status, timestamp=None, event_id=None):
    if status not in VALID_STATUSES:
        raise ValueError('unknown scoring status')
    service_id = _required(service, 'id', str)
    points = _required(service, 'points', int)
    penalty = _required(service, 'sla_penalty', int)
    if points < 0 or penalty < 0:
        raise ConfigurationError('points and sla_penalty must not be negative')
    if event_id is None:
        row = db.execute(
            'SELECT consecutive_failures,total_points,total_sla_deductions FROM service_state WHERE service_id=?',
            (service_id,),
        ).fetchone() or (0, 0, 0)
    else:
        row = db.execute(
            '''SELECT consecutive_failures,total_points,total_sla_deductions
               FROM event_service_state WHERE event_id=? AND service_id=?''',
            (event_id, service_id),
        ).fetchone() or (0, 0, 0)
    failures, total_points, total_deductions = row
    awarded = deduction = 0
    if status == 'PASS':
        failures = 0
        awarded = points
    elif status == 'DOWN':
        failures += 1
        if failures >= FAILURES_PER_SLA:
            deduction = penalty
            failures = 0
    if event_id is None:
        db.execute('''INSERT INTO service_state(
                service_id,consecutive_failures,total_points,total_sla_deductions,last_status,last_timestamp)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(service_id) DO UPDATE SET
                consecutive_failures=excluded.consecutive_failures,
                total_points=excluded.total_points,
                total_sla_deductions=excluded.total_sla_deductions,
                last_status=excluded.last_status,last_timestamp=excluded.last_timestamp''',
            (service_id, failures, total_points + awarded, total_deductions + deduction, status, timestamp))
    else:
        db.execute('''INSERT INTO event_service_state(
                event_id,service_id,consecutive_failures,total_points,total_sla_deductions,
                last_status,last_timestamp)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(event_id,service_id) DO UPDATE SET
                consecutive_failures=excluded.consecutive_failures,
                total_points=excluded.total_points,
                total_sla_deductions=excluded.total_sla_deductions,
                last_status=excluded.last_status,last_timestamp=excluded.last_timestamp''',
            (event_id, service_id, failures, total_points + awarded,
             total_deductions + deduction, status, timestamp))
    return {'awarded_points': awarded, 'sla_deduction': deduction, 'consecutive_failures': failures}


def record_round(db, services, observations, timestamp, expected_event_id=None):
    initialize_schema(db)
    if expected_event_id is not None:
        from lifecycle import get_current_event
        db.execute('BEGIN IMMEDIATE')
        current = get_current_event(db)
        if current.id != expected_event_id or current.state != 'RUNNING':
            db.rollback()
            return None
    try:
        if expected_event_id is None:
            cursor = db.execute('INSERT INTO scoring_rounds(timestamp) VALUES(?)', (timestamp,))
        else:
            cursor = db.execute(
                'INSERT INTO scoring_rounds(timestamp,event_id) VALUES(?,?)',
                (timestamp, expected_event_id),
            )
        round_id = cursor.lastrowid
        total_awarded = total_deductions = 0
        for service in services:
            status, reason, latency = observations[service['id']]
            scoring = apply_scoring_result(
                db, service, status, timestamp, event_id=expected_event_id,
            )
            total_awarded += scoring['awarded_points']
            total_deductions += scoring['sla_deduction']
            values = (
                round_id, timestamp, service['id'], service.get('host_name', service['id']),
                service.get('service_name', service['id']), status, reason, latency,
                scoring['awarded_points'], scoring['sla_deduction'],
                scoring['consecutive_failures'],
            )
            if expected_event_id is None:
                db.execute('''INSERT INTO service_checks(
                    round_id,timestamp,service_id,host_name,service_name,status,reason,latency_ms,
                    awarded_points,sla_deduction,consecutive_failures)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''', values)
            else:
                db.execute('''INSERT INTO service_checks(
                    round_id,timestamp,service_id,host_name,service_name,status,reason,latency_ms,
                    awarded_points,sla_deduction,consecutive_failures,event_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', values + (expected_event_id,))
        db.execute('UPDATE scoring_rounds SET points_awarded=?,sla_deductions=?,net_points=? WHERE id=?',
                   (total_awarded, total_deductions, total_awarded - total_deductions, round_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return round_id


def resolve_services(config):
    services = _required(config, 'services', list)
    mode = config.get('forum_web_mode', 'http')
    resolved = []
    seen = set()
    for original in services:
        if not isinstance(original, dict):
            raise ConfigurationError('each service must be an object')
        service = dict(original)
        variants = service.pop('variants', None)
        if variants is not None:
            if service.get('id') != 'forum01-web' or mode not in variants:
                raise ConfigurationError('forum web mode is invalid')
            service.update(variants[mode])
        service_id = _required(service, 'id', str)
        if service_id in seen:
            raise ConfigurationError('service IDs must be unique')
        seen.add(service_id)
        _required(service, 'points', int)
        _required(service, 'sla_penalty', int)
        resolved.append(service)
    if not resolved:
        raise ConfigurationError('at least one service is required')
    return resolved


def set_forum_mode(config, mode, db):
    if mode not in {'http', 'https'}:
        raise ConfigurationError('forum mode must be http or https')
    config['forum_web_mode'] = mode
    resolved = resolve_services(config)
    lifecycle_tables = db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='scorer_settings'"
    ).fetchone()[0]
    if lifecycle_tables:
        from lifecycle import current_event_id
        db.execute(
            'UPDATE event_service_state SET consecutive_failures=0 WHERE event_id=? AND service_id=?',
            (current_event_id(db), 'forum01-web'),
        )
    else:
        db.execute('UPDATE service_state SET consecutive_failures=0 WHERE service_id=?', ('forum01-web',))
    db.commit()
    return resolved


def _load_config(path):
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ConfigurationError('configuration file cannot be read') from error
    if not isinstance(config, dict):
        raise ConfigurationError('configuration root must be an object')
    return config


def _write_config(path, config):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def render_report(db, public, services=None, control_token=''):
    from reporting import render_report as render_pages
    render_pages(db, public, services, control_token=control_token)


def _load_control_token(database_path):
    try:
        return (Path(database_path).parent / 'control-token').read_text(
            encoding='ascii'
        ).strip()
    except OSError:
        return ''


def run_scoring_round(config_path=None, database_path=None, public_path=None):
    config_path = Path(config_path or BASE / 'config.json')
    database_path = Path(database_path or BASE / 'state' / 'results.sqlite3')
    public_path = Path(public_path or BASE / 'public')
    config = _load_config(config_path)
    services = resolve_services(config)
    control_token = _load_control_token(database_path)
    observations = {}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    public_path.mkdir(mode=0o755, parents=True, exist_ok=True)
    from lifecycle import get_current_event, migrate_lifecycle
    with closing(sqlite3.connect(database_path)) as db, db:
        initialize_schema(db)
        event = migrate_lifecycle(db, timestamp)
        portal=None
        if config.get('portal_database'):
            try:
                from portal_store import PortalStore
                from inject_services import active_services
                portal=PortalStore(config['portal_database'],database_path,config_path)
                portal._release_due({'id':event.id,'state':event.state},time.time())
                dynamic=active_services(config['portal_database'],event.id)
                for task in active_services(config['portal_database'],event.id,include_grace=True):
                    if task['probe']=='https_upgrade' and task['host']=='10.77.30.20':
                        for service in services:
                            if service['id']=='forum01-web' and service['probe']=='http':
                                service['redirect_origin']='https://'+task['server_name']+task['path']
                services+=dynamic
            except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
                portal=None
                print('Inject configuration unavailable; baseline service scoring continues.',file=sys.stderr)
        if event.state != 'RUNNING':
            render_report(db, public_path, services, control_token=control_token)
            result = {
                'time': timestamp, 'event_id': event.id, 'event_state': event.state,
                'recorded': False, 'round_id': None, 'points_awarded': 0,
                'sla_deductions': 0, 'net_points': 0, 'services': {},
            }
            print(json.dumps(result, sort_keys=True), flush=True)
            return result

    def observe(service):
        started = time.monotonic()
        status, reason = run_probe(service)
        return service['id'], (status, reason, round(1000 * (time.monotonic() - started)))

    workers = min(int(config.get('max_workers', 8)), len(services))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for service_id, observation in pool.map(observe, services):
            observations[service_id] = observation
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')
    with closing(sqlite3.connect(database_path)) as db, db:
        round_id = record_round(
            db, services, observations, timestamp, expected_event_id=event.id,
        )
        render_report(db, public_path, services, control_token=control_token)
        current = get_current_event(db)
        summary = db.execute(
            'SELECT points_awarded,sla_deductions,net_points FROM scoring_rounds WHERE id=?',
            (round_id,),
        ).fetchone() if round_id is not None else (0, 0, 0)
    if portal is not None and round_id is not None:
        try: portal.sync_services({'id':event.id,'state':event.state},time.time())
        except (OSError,sqlite3.Error,ValueError): print('Inject awards pending synchronization; service round retained.',file=sys.stderr)
    result = {
        'time': timestamp, 'event_id': current.id, 'event_state': current.state,
        'recorded': round_id is not None, 'round_id': round_id,
        'points_awarded': summary[0], 'sla_deductions': summary[1],
        'net_points': summary[2], 'services': observations,
    }
    print(json.dumps(result, sort_keys=True), flush=True)
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'set-forum-mode':
        if len(argv) != 2:
            raise SystemExit('usage: scorer.py set-forum-mode http|https')
        config_path = BASE / 'config.json'
        config = _load_config(config_path)
        with sqlite3.connect(BASE / 'state' / 'results.sqlite3') as db:
            initialize_schema(db)
            set_forum_mode(config, argv[1], db)
        _write_config(config_path, config)
        print(f'forum01 web scoring mode set to {argv[1]}; its failure counter was reset')
        return
    if argv:
        raise SystemExit('usage: scorer.py [set-forum-mode http|https]')
    run_scoring_round()


if __name__ == '__main__':
    main()
