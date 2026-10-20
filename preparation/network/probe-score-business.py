import concurrent.futures, json, sys, sqlite3, ftplib, hashlib
from pathlib import Path
sys.path.insert(0,'/home/jwang/summit-scoring')
import scorer
config=json.loads(Path('/home/jwang/summit-scoring/config.json').read_text())
selected=[s for s in scorer.resolve_services(config) if s.get('host_name') in sys.argv[1:]]
def probe(s):
    status,detail=scorer.run_probe(s)
    return {'id':s['id'],'status':status,'detail':detail}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    print(json.dumps(list(pool.map(probe,selected)),indent=2))
if 'forum01' in sys.argv[1:]:
    c=sqlite3.connect('file:/home/jwang/summit-portal/portal-state/portal.sqlite3?mode=ro',uri=True)
    rows=c.execute("SELECT service_json FROM injects WHERE code='I02' AND service_json IS NOT NULL ORDER BY id DESC").fetchall()
    for row in rows:
        s=json.loads(row[0])
        if s.get('probe')!='ftp_share' or not s.get('password'): continue
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(s['host'],21,timeout=5); ftp.login(s['username'],s['password'])
                host,port=ftp.makepasv()
                if host!=s['host'] or not 40000<=port<=40049: raise RuntimeError('Unexpected passive endpoint')
                digest=hashlib.sha256()
                ftp.retrbinary('RETR '+s['file'],digest.update)
            print(json.dumps({'passive_ftp':'PASS','port':port,'expected_content':digest.hexdigest()==s['sha256']}))
        except Exception as e:
            print(json.dumps({'passive_ftp':'NOT_VERIFIED','reason':type(e).__name__}))
        break
