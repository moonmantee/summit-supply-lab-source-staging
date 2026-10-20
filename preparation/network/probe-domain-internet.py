import concurrent.futures
import socket
import struct
import urllib.request

print('HOST', socket.gethostname(), flush=True)

def tcp(port):
    try:
        with socket.create_connection(('10.77.40.10', port), timeout=3):
            return f'AD TCP {port} PASS'
    except OSError as error:
        return f'AD TCP {port} FAIL: {error}'

with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
    for result in pool.map(tcp, [53, 88, 135, 389, 445, 464, 3268]):
        print(result, flush=True)

name = '_ldap._tcp.dc._msdcs.corp.summit.test'
question = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\0'
packet = struct.pack('!6H', 0x4343, 0x0100, 1, 0, 0, 0) + question + struct.pack('!HH', 33, 1)
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(3)
        client.sendto(packet, ('10.77.40.10', 53))
        response, _ = client.recvfrom(4096)
    _, flags, _, answers, _, _ = struct.unpack('!6H', response[:12])
    print('AD DNS SRV', 'PASS' if flags & 15 == 0 and answers else 'FAIL', 'answers', answers, flush=True)
except OSError as error:
    print('AD DNS SRV FAIL:', error, flush=True)

try:
    print('PUBLIC DNS', socket.getaddrinfo('example.com', 443)[0][4][0], flush=True)
    with urllib.request.urlopen('https://example.com', timeout=10) as response:
        print('INTERNET HTTPS', response.status, flush=True)
except Exception as error:
    print('INTERNET HTTPS FAIL:', error, flush=True)
