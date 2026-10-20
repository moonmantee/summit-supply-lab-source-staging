import concurrent.futures, json, socket, struct, urllib.request
ip=socket.gethostbyname(socket.gethostname())
checks=[]
def tcp(dst,port):
    try:
        with socket.create_connection((dst,port),3): return [dst,port,'PASS']
    except OSError as e: return [dst,port,'FAIL',str(e)]
targets=[('10.77.40.10',p) for p in [53,88,135,389,445,464,3268]]
targets += [('10.77.70.10',p) for p in [8080,8771,8772]]
if socket.gethostname().lower().startswith('workstation'):
    targets += [('10.77.30.10',443),('10.77.30.20',80),('10.77.30.30',25),('10.77.30.30',143),('10.77.50.20',3306)]
if socket.gethostname().lower().startswith('shop'):
    targets += [('10.77.50.20',3306)]
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool: checks.extend(pool.map(lambda x:tcp(*x),targets))
name='_ldap._tcp.dc._msdcs.corp.summit.test'
question=b''.join(bytes([len(p)])+p.encode() for p in name.split('.'))+b'\0'
packet=struct.pack('!6H',0x4343,0x0100,1,0,0,0)+question+struct.pack('!HH',33,1)
try:
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.settimeout(3); s.sendto(packet,('10.77.40.10',53)); data,_=s.recvfrom(4096)
    _,flags,_,answers,_,_=struct.unpack('!6H',data[:12]); checks.append(['AD SRV','PASS' if flags&15==0 and answers else 'FAIL'])
except OSError as e: checks.append(['AD SRV','FAIL',str(e)])
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for url in ['https://example.com','http://10.77.70.10:8080/portal/']:
    try:
        with opener.open(url,timeout=10) as r: checks.append([url,'PASS',r.status])
    except Exception as e: checks.append([url,'FAIL',str(e)])
print(json.dumps({'host':socket.gethostname(),'checks':checks},indent=2))
