"""Bounded Unix-domain client shared by the CLI and CALDERA plugin."""
import json
import socket
SOCKET = '/run/summit-caldera-admin/control.sock'
REQUEST_LIMIT = 256 * 1024
RESPONSE_LIMIT = 512 * 1024


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    def invalid(value): raise ValueError('Nonfinite JSON value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


class AdminClient:
    def __init__(self, path=SOCKET): self.path = path

    def call(self, request, actor='local:root'):
        body = json.dumps(dict(request=request, actor=actor), allow_nan=False).encode()+b'\n'
        if len(body) > REQUEST_LIMIT: raise ValueError('Request exceeds 256 KiB')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2); client.connect(self.path); client.settimeout(5)
            client.sendall(body)
            chunks = bytearray()
            while len(chunks) <= RESPONSE_LIMIT:
                chunk = client.recv(min(65536, RESPONSE_LIMIT+1-len(chunks)))
                if not chunk: break
                chunks.extend(chunk)
                if chunks.endswith(b'\n'): break
            if len(chunks) > RESPONSE_LIMIT or not chunks.endswith(b'\n'): raise ValueError('Invalid controller response size/framing')
            result = strict_json(chunks)
            if not isinstance(result, dict) or type(result.get('ok')) is not bool: raise ValueError('Invalid controller response')
            return result
