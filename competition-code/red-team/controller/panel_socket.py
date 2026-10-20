"""Local management socket; guest network protocol is unchanged."""
import json
import os
import pathlib
import socket
import socketserver
import struct
import threading
from fixture_contract import strict_json
from panel_client import REQUEST_LIMIT, RESPONSE_LIMIT


class AdminServer:
    def __init__(self, path, service, allowed_uids):
        self.path, self.service, self.allowed_uids = path, service, allowed_uids
        self.server = self.thread = None

    def start(self):
        owner = self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(5)
                result = dict(ok=False, error=dict(code='unauthorized', message='Management peer denied', rows=[]))
                try:
                    uid = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
                    if uid in owner.allowed_uids:
                        raw = self.rfile.readline(REQUEST_LIMIT+1)
                        if len(raw) > REQUEST_LIMIT or not raw.endswith(b'\n'): raise ValueError('Invalid frame')
                        body = strict_json(raw)
                        if not isinstance(body, dict) or set(body) != {'request', 'actor'}: raise ValueError('Invalid envelope')
                        actor = 'local:root' if uid == 0 else body['actor']
                        result = owner.service.handle(body['request'], actor)
                except (ValueError, KeyError, TypeError):
                    result = dict(ok=False, error=dict(code='invalid', message='Invalid management request', rows=[]))
                except Exception:
                    result = dict(ok=False, error=dict(code='unavailable', message='Controller unavailable', rows=[]))
                try:
                    raw = json.dumps(result, allow_nan=False).encode()+b'\n'
                    if len(raw) > RESPONSE_LIMIT:
                        raw = b'{"ok":false,"error":{"code":"limit","message":"Response exceeds 512 KiB","rows":[]}}\n'
                    self.wfile.write(raw)
                except (OSError, ValueError): pass
        path = pathlib.Path(self.path)
        if path.exists():
            # A live or unexpected socket must not be replaced.
            import stat
            if not stat.S_ISSOCK(path.lstat().st_mode): raise ValueError('Unexpected management socket object')
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(1)
                try: probe.connect(self.path)
                except ConnectionRefusedError: path.unlink()
                else: raise ValueError('Management socket already active')
        self.server = socketserver.UnixStreamServer(self.path, Handler)
        os.chmod(self.path, 0o660)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        self.thread.start()

    def close(self):
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.thread.join(6)
            pathlib.Path(self.path).unlink(missing_ok=True)
