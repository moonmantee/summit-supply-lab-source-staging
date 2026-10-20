import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

import scorer
from lifecycle import get_current_event, migrate_lifecycle


class ControlServerTestCase(unittest.TestCase):
    def setUp(self):
        import scoreboard_server
        self.server_module = scoreboard_server
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'state' / 'results.sqlite3'
        self.public = self.root / 'public'
        self.public.mkdir(parents=True)
        (self.public / 'index.html').write_text('initial')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'services': [{
                'id': 'test-ssh', 'host_name': 'test01', 'service_name': 'SSH',
                'probe': 'banner', 'host': '127.0.0.1', 'port': 9,
                'banner_prefix': 'SSH-', 'points': 1, 'sla_penalty': 5,
            }]
        }))
        self.token_path = self.root / 'state' / 'control-token'
        self.token = scoreboard_server.load_or_create_token(self.token_path)
        with sqlite3.connect(self.database) as db:
            scorer.initialize_schema(db)
            migrate_lifecycle(db, '2026-10-02T01:00:00+00:00')

        module = self.server_module

        class TestHandler(module.ControlHandler):
            database_path = self.database
            public_path = self.public
            config_path = self.config
            control_token = self.token

            def log_message(self, *_args):
                pass

        self.httpd = module.ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    @property
    def port(self):
        return self.httpd.server_address[1]

    def request(self, method='POST', body=None, token=None, host=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        headers = {
            'Host': host or f'127.0.0.1:{self.port}',
            'Content-Type': 'application/json',
            'X-Summit-Control-Token': self.token if token is None else token,
        }
        if origin is not None:
            headers['Origin'] = origin
        payload = json.dumps(body).encode() if isinstance(body, dict) else body
        connection.request(method, '/api/control', body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        try:
            decoded = json.loads(data or b'{}')
        except json.JSONDecodeError:
            decoded = {'raw': data.decode(errors='replace')}
        return response.status, response.getheaders(), decoded

    def state(self):
        with sqlite3.connect(self.database) as db:
            return get_current_event(db)


class ControlSecurityTests(ControlServerTestCase):
    def test_systemd_unit_runs_hardened_control_server(self):
        unit = (Path(__file__).resolve().parent / 'summit-scoreboard.service').read_text()
        self.assertIn('ExecStart=/usr/bin/python3 /home/jwang/summit-scoring/scoreboard_server.py', unit)
        self.assertIn('NoNewPrivileges=true', unit)
        self.assertIn('PrivateTmp=true', unit)

    def test_token_file_created_with_user_only_permissions(self):
        self.assertGreaterEqual(len(self.token), 32)
        self.assertEqual(os.stat(self.token_path).st_mode & 0o777, 0o600)
        self.assertEqual(
            self.server_module.load_or_create_token(self.token_path),
            self.token,
        )

    def test_get_cannot_mutate(self):
        status, _, _ = self.request(method='GET')
        self.assertEqual(status, 405)
        self.assertEqual(self.state().state, 'READY')

    def test_bad_token_is_forbidden(self):
        status, _, _ = self.request(body={'action': 'start'}, token='wrong')
        self.assertEqual(status, 403)
        self.assertEqual(self.state().state, 'READY')

    def test_non_loopback_host_or_origin_is_forbidden(self):
        bad_host, _, _ = self.request(body={'action': 'start'}, host='score.example:8766')
        bad_origin, _, _ = self.request(
            body={'action': 'start'}, origin='https://score.example'
        )
        self.assertEqual((bad_host, bad_origin), (403, 403))
        self.assertEqual(self.state().state, 'READY')

    def test_unknown_action_and_malformed_json_are_rejected(self):
        unknown, _, _ = self.request(body={'action': 'erase'})
        malformed, _, _ = self.request(body=b'{not-json')
        oversized, _, _ = self.request(body=b'x' * 2048)
        self.assertEqual((unknown, malformed, oversized), (400, 400, 413))
        self.assertEqual(self.state().state, 'READY')

    def test_dynamic_text_cannot_inject_headers_or_html(self):
        marker = '<script>alert(1)</script>\r\nX-Injected: yes'
        status, headers, payload = self.request(
            body={'action': 'start', 'name': marker}
        )
        self.assertEqual(status, 400)
        self.assertNotIn(marker, str(headers))
        self.assertNotIn(marker, json.dumps(payload))
        self.assertEqual(self.state().name, 'Competition 1')


class ControlActionTests(ControlServerTestCase):
    def test_start_stop_reset_return_new_state_and_render(self):
        start, _, started = self.request(body={'action': 'start'})
        stop, _, stopped = self.request(body={'action': 'stop'})
        reset, _, replacement = self.request(body={'action': 'reset'})

        self.assertEqual((start, stop, reset), (200, 200, 200))
        self.assertEqual((started['state'], stopped['state'], replacement['state']),
                         ('RUNNING', 'STOPPED', 'READY'))
        self.assertEqual(replacement['name'], 'Competition 2')
        self.assertTrue((self.public / 'index.html').exists())
        self.assertTrue((self.public / 'history-event-1.html').exists())
        self.assertTrue((self.public / 'history-event-2.html').exists())

    def test_illegal_transition_returns_conflict_without_change(self):
        status, _, payload = self.request(body={'action': 'stop'})
        self.assertEqual(status, 409)
        self.assertIn('Cannot stop', payload['error'])
        self.assertEqual(self.state().state, 'READY')

    def test_render_failure_does_not_rollback_committed_state(self):
        with mock.patch.object(
            self.server_module.scorer, 'render_report', side_effect=OSError('render failed')
        ):
            status, _, payload = self.request(body={'action': 'start'})

        self.assertEqual(status, 500)
        self.assertIn('render', payload['error'].lower())
        self.assertEqual(self.state().state, 'RUNNING')


if __name__ == '__main__':
    unittest.main()
