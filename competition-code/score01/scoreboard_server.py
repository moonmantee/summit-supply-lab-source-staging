"""Localhost-only static scoreboard and organizer lifecycle controls."""
import datetime as dt
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

import scorer
from lifecycle import LifecycleError, migrate_lifecycle, transition_event


BASE = Path(__file__).resolve().parent
MAX_CONTROL_BODY = 1024


def load_or_create_token(path: Path) -> str:
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
            stream.write(secrets.token_urlsafe(32) + '\n')
    os.chmod(path, 0o600)
    token = path.read_text(encoding='ascii').strip()
    if len(token) < 32:
        raise RuntimeError('control token is missing or too short')
    return token


def _loopback_authority(value):
    if not value:
        return False
    try:
        parsed = urlsplit(value if '://' in value else '//' + value)
        return parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
    except ValueError:
        return False


class ControlHandler(SimpleHTTPRequestHandler):
    database_path = BASE / 'state' / 'results.sqlite3'
    public_path = BASE / 'public'
    config_path = BASE / 'config.json'
    control_token = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.public_path), **kwargs)

    def _send_json(self, status, payload):
        body = json.dumps(payload, sort_keys=True).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def _valid_request_origin(self):
        if not _loopback_authority(self.headers.get('Host', '')):
            return False
        origin = self.headers.get('Origin')
        return origin is None or _loopback_authority(origin)

    def do_GET(self):
        if urlsplit(self.path).path == '/api/control':
            self._send_json(405, {'error': 'Control actions require POST'})
            return
        if not self._valid_request_origin():
            self._send_json(403, {'error': 'Loopback access required'})
            return
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != '/api/control':
            self._send_json(404, {'error': 'Unknown endpoint'})
            return
        if not self._valid_request_origin():
            self._send_json(403, {'error': 'Loopback Host and Origin required'})
            return
        supplied = self.headers.get('X-Summit-Control-Token', '')
        if not self.control_token or not hmac.compare_digest(supplied, self.control_token):
            self._send_json(403, {'error': 'Invalid control token'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self._send_json(400, {'error': 'Invalid content length'})
            return
        if length > MAX_CONTROL_BODY:
            self._send_json(413, {'error': 'Control request is too large'})
            return
        if length <= 0:
            self._send_json(400, {'error': 'JSON body is required'})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {'error': 'Malformed JSON'})
            return
        if not isinstance(payload, dict) or set(payload) != {'action'}:
            self._send_json(400, {'error': 'Only an action field is accepted'})
            return
        action = payload['action']
        if action not in {'start', 'stop', 'reset'}:
            self._send_json(400, {'error': 'Unknown control action'})
            return
        self._apply_control(action)

    def _apply_control(self, action):
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        try:
            config = scorer._load_config(self.config_path)
            services = scorer.resolve_services(config)
            with sqlite3.connect(self.database_path) as db:
                scorer.initialize_schema(db)
                migrate_lifecycle(db, now)
                event = transition_event(db, action, now)
            try:
                with sqlite3.connect(self.database_path) as db:
                    scorer.render_report(
                        db, self.public_path, services,
                        control_token=self.control_token,
                    )
            except Exception:
                self._send_json(500, {
                    'error': 'Competition state changed, but dashboard rendering failed',
                    'state': event.state,
                })
                return
            self._send_json(200, {
                'event_id': event.id,
                'name': event.name,
                'state': event.state,
            })
        except LifecycleError as error:
            self._send_json(409, {'error': str(error)})
        except (OSError, ValueError, sqlite3.Error):
            self._send_json(500, {'error': 'Control operation failed safely'})


def prepare_server(database_path=None, public_path=None, config_path=None, token_path=None):
    database_path = Path(database_path or BASE / 'state' / 'results.sqlite3')
    public_path = Path(public_path or BASE / 'public')
    config_path = Path(config_path or BASE / 'config.json')
    token_path = Path(token_path or BASE / 'state' / 'control-token')
    token = load_or_create_token(token_path)
    config = scorer._load_config(config_path)
    services = scorer.resolve_services(config)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as db:
        scorer.initialize_schema(db)
        migrate_lifecycle(db, now)
        scorer.render_report(db, public_path, services, control_token=token)
    return token


def serve(host='127.0.0.1', port=8766):
    token = prepare_server()
    ControlHandler.control_token = token
    server = ThreadingHTTPServer((host, port), ControlHandler)
    server.serve_forever()


if __name__ == '__main__':
    serve()
