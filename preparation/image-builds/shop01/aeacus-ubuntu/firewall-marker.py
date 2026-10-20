"""Disposable nonprivileged TCP marker for firewall reachability rehearsal."""
import socketserver
class Marker(socketserver.BaseRequestHandler):
    def handle(self):
        try: self.request.sendall(b'SUMMIT-FIREWALL-MARKER\n')
        except OSError: pass
class Server(socketserver.TCPServer): allow_reuse_address=True
with Server(('0.0.0.0',30303),Marker) as server: server.serve_forever()
