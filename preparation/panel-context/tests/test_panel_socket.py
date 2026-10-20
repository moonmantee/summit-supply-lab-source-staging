import os
import pathlib
import socket
import sys
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'payload/controller'))
try:
    from panel_socket import AdminServer
    from panel_client import AdminClient
except ImportError: AdminServer = AdminClient = None


class SocketTests(unittest.TestCase):
    def test_transport_implemented(self):
        self.assertIsNotNone(AdminServer, 'private admin transport missing')

    @unittest.skipUnless(hasattr(socket, 'SO_PEERCRED'), 'Linux peer credentials required')
    def test_real_socket_and_peer_denial(self):
        class Service:
            def handle(self, request, actor): return dict(ok=True, data=dict(op=request['op'], actor=actor))
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp)/'control.sock')
            server = AdminServer(path, Service(), {os.getuid()}); server.start()
            try:
                result = AdminClient(path).call({'op':'status','args':{}}, actor='session:organizer')
                self.assertTrue(result['ok'])
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o660)
                for raw in [b'{"request":{},"request":{},"actor":"x"}\n', b'{"request":{"op":NaN},"actor":"x"}\n', b'x'*262146+b'\n']:
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(6); client.connect(path); client.sendall(raw)
                        self.assertIn(b'false', client.recv(4096))
            finally: server.close()
            server = AdminServer(path, Service(), {os.getuid()+10000}); server.start()
            try: self.assertFalse(AdminClient(path).call({'op':'status','args':{}})['ok'])
            finally: server.close()

if __name__ == '__main__': unittest.main()
