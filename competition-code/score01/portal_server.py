"""Authenticated team portal; organizer operations are direct-loopback only."""
import argparse
import base64
import getpass
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from portal_store import PortalStore,EventChanged

BASE=Path(__file__).resolve().parent
COOKIE='summit_portal'
MAX_BODY=3*1024*1024
SESSION_SECONDS=8*3600


def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),210000).hex()


def write_auth(path,team_password,admin_password):
    if min(len(team_password),len(admin_password))<14: raise ValueError('Passwords require at least 14 characters.')
    data={}
    for role,password in [('team',team_password),('admin',admin_password)]:
        salt=secrets.token_hex(16); data[role]={'salt':salt,'hash':password_hash(password,salt)}
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.new')
    with open(temporary,'w',encoding='utf-8') as stream: json.dump(data,stream)
    temporary.chmod(0o600); temporary.replace(path)


class PortalHTTPServer(ThreadingHTTPServer):
    daemon_threads=True


def make_server(store,auth_path,files_path,host='127.0.0.1',port=8767,allowed_hosts=None):
    allowed=set(allowed_hosts or ['10.77.70.10:8080'])
    files=Path(files_path).resolve()
    assets=BASE/'portal-web'

    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'

        def setup(self):
            super().setup(); self.connection.settimeout(15)

        def log_message(self,format,*args):
            # Never log bodies, query strings, cookies, or credentials.
            pass

        def response(self,status,data,mime='application/json; charset=utf-8',extra=None):
            if isinstance(data,(dict,list)): data=json.dumps(data).encode()
            elif isinstance(data,str): data=data.encode()
            self.send_response(status)
            for key,value in {
                'Content-Type':mime,'Content-Length':str(len(data)),
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                'Referrer-Policy':'same-origin','X-Frame-Options':'DENY',
                'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                **(extra or {})}.items(): self.send_header(key,value)
            self.end_headers(); self.wfile.write(data)

        def direct(self):
            try: name=urlsplit('//'+self.headers.get('Host','')).hostname
            except ValueError: return False
            return name in {'127.0.0.1','localhost','::1'} and self.client_address[0] in {'127.0.0.1','::1'} and self.headers.get('X-Portal-Proxied')!='1'

        def valid_host(self):
            return self.direct() or self.headers.get('Host','') in allowed

        def valid_origin(self):
            origin=self.headers.get('Origin')
            try:
                p=urlsplit(origin or '')
                return p.scheme in {'http','https'} and p.netloc==self.headers.get('Host','') and not p.path and not p.query
            except ValueError: return False

        def auth_data(self):
            raw=Path(auth_path).read_bytes()
            return json.loads(raw),hashlib.sha256(raw).hexdigest()

        def session(self):
            try:
                cookie=SimpleCookie(self.headers.get('Cookie',''))
                token=cookie[COOKIE].value
                if len(token)>100: return None
                digest=hashlib.sha256(token.encode()).hexdigest()
                _,version=self.auth_data()
                with store.db() as db:
                    row=db.execute('SELECT * FROM sessions WHERE hash=? AND expires>? AND auth_version=?',(digest,time.time(),version)).fetchone()
                if row is None: return None
                if row['role']=='admin' and not self.direct(): return None
                return dict(row)
            except (KeyError,ValueError,OSError,TypeError): return None

        def login(self,payload):
            role=payload.get('username'); password=payload.get('password')
            if role=='admin' and not self.direct(): self.response(403,{'error':'Organizer login requires the private loopback connection.'}); return
            valid_input=role in {'team','admin'} and isinstance(password,str) and len(password)<=200
            client=self.headers.get('X-Portal-Client-IP',self.client_address[0]) if self.headers.get('X-Portal-Proxied')=='1' else self.client_address[0]
            now=time.time()
            with store.db() as db:
                row=db.execute('SELECT failures,until FROM login_limits WHERE client=?',(client,)).fetchone()
                if row and row['failures']>=5 and row['until']>now:
                    self.response(429,{'error':'Too many attempts. Try again after 15 minutes.'}); return
                failures=(row['failures'] if row and row['until']>now else 0)+1
                db.execute('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)',(client,failures,now+900))
            if not valid_input:
                self.response(401,{'error':'Incorrect username or password.'}); return
            auth,version=self.auth_data(); record=auth[role]
            if not hmac.compare_digest(password_hash(password,record['salt']),record['hash']):
                self.response(401,{'error':'Incorrect username or password.'}); return
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
            with store.db() as db:
                db.execute('DELETE FROM login_limits WHERE client=?',(client,))
                db.execute('DELETE FROM sessions WHERE expires<=?',(now,))
                db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),role,csrf,now+SESSION_SECONDS,version))
            self.response(200,{'role':role,'csrf':csrf},extra={'Set-Cookie':f'{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/portal/; Max-Age={SESSION_SECONDS}'})

        def do_GET(self):
            try: self.get_request()
            except (OSError,sqlite3.Error): self.response(503,{'error':'Portal storage is unavailable. Contact White Team.'})

        def get_request(self):
            if not self.valid_host(): self.response(403,{'error':'Invalid portal address.'}); return
            path=urlsplit(self.path).path
            if path in {'/','/portal'}:
                self.response(302,b'',extra={'Location':'/portal/'}); return
            public={'/portal/':'index.html','/portal/app.js':'app.js','/portal/style.css':'style.css'}
            if path in public:
                file=assets/public[path]
                if not file.is_file(): self.response(503,{'error':'Portal assets are unavailable.'}); return
                self.response(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream'); return
            session=self.session()
            if session is None: self.response(401,{'error':'Sign in to the team portal.'}); return
            if path in {'/portal/scoreboard/','/portal/scoreboard/index.html','/portal/scoreboard/history.html'}:
                from portal_scoreboard import page
                self.response(200,page(store,history=path.endswith('history.html')),'text/html; charset=utf-8',{'X-Frame-Options':'SAMEORIGIN','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"}); return
            if path in {'/portal/scoreboard/scoreboard.css','/portal/scoreboard/scoreboard.js'}:
                file=BASE/path.rsplit('/',1)[1]
                self.response(200,file.read_bytes(),mimetypes.guess_type(file.name)[0]); return
            if path=='/portal/api/state':
                data=store.snapshot(admin=session['role']=='admin')
                data.update(role=session['role'],csrf=session['csrf'])
                self.response(200,data); return
            if path=='/portal/files/README.md':
                file=files/'README.md'
                if not file.is_file(): self.response(404,{'error':'README has not been published.'}); return
                self.response(200,file.read_bytes(),'text/plain; charset=utf-8'); return
            if path=='/portal/files/README.docx':
                file=files/'README.docx'
                if not file.is_file(): self.response(404,{'error':'Word README has not been published.'}); return
                self.response(200,file.read_bytes(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document',{'Content-Disposition':'attachment; filename="Summit-Blue-Team-README.docx"'}); return
            if path.startswith('/portal/attachments/'):
                try:
                    ident=int(path.rsplit('/',1)[1]); state=store.snapshot(admin=session['role']=='admin')
                    permitted={a['id'] for c in state['injects'] for a in c['attachments']}
                    if ident not in permitted: raise ValueError('Attachment is not released.')
                    with store.db() as db: row=db.execute('SELECT name,stored_name FROM attachments WHERE id=?',(ident,)).fetchone()
                    file=files/'attachments'/row['stored_name']
                    if not file.is_file() or file.is_symlink() or file.resolve().parent!=(files/'attachments').resolve(): raise ValueError('Attachment unavailable.')
                    self.response(200,file.read_bytes(),'application/octet-stream',{'Content-Disposition':f'attachment; filename="{row["name"]}"'})
                except (ValueError,TypeError,OSError): self.response(404,{'error':'Attachment is unavailable.'})
                return
            self.response(404,{'error':'Page not found.'})

        def do_POST(self):
            if not self.valid_host() or not self.valid_origin():
                self.close_connection=True
                self.response(403,{'error':'Same-origin portal requests are required.'}); return
            if self.headers.get('Transfer-Encoding'):
                self.response(400,{'error':'Unsupported request encoding.'}); self.close_connection=True; return
            try:
                try: length=int(self.headers.get('Content-Length','0'))
                except ValueError:
                    self.close_connection=True
                    raise ValueError('Invalid content length.')
                if len(self.headers.get_all('Content-Length',[]))!=1:
                    self.close_connection=True
                    raise ValueError('Exactly one content length is required.')
                if not 0<length<=MAX_BODY: self.response(413,{'error':'Request exceeds the portal limit.'}); self.close_connection=True; return
                if self.headers.get_content_type()!='application/json':
                    self.close_connection=True
                    raise ValueError('JSON is required.')
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict): raise ValueError('A JSON object is required.')
                path=urlsplit(self.path).path
                if path=='/portal/api/login': self.login(payload); return
                session=self.session()
                if session is None: self.response(401,{'error':'Your session has ended. Sign in again.'}); return
                if not hmac.compare_digest(self.headers.get('X-Portal-CSRF',''),session['csrf']): self.response(403,{'error':'Invalid session request. Refresh the page.'}); return
                if path=='/portal/api/logout':
                    with store.db() as db: db.execute('DELETE FROM sessions WHERE hash=?',(session['hash'],))
                    self.response(200,{'ok':True},extra={'Set-Cookie':f'{COOKIE}=; Path=/portal/; HttpOnly; SameSite=Strict; Max-Age=0'}); return
                if path in {'/portal/api/admin','/portal/api/inject'}:
                    expected=payload.get('event_id')
                    if isinstance(expected,bool) or not isinstance(expected,int): raise ValueError('Refresh the portal before submitting this event action.')
                    if expected!=store.event()['id']:
                        self.response(409,{'error':'The event changed. Refresh and review the new event before submitting.'}); return
                if path=='/portal/api/inject':
                    if session['role']!='team': raise ValueError('Use the team account to submit an inject.')
                    store.team_action(self.ident(payload),payload.get('action'),expected_event_id=expected)
                elif path=='/portal/api/admin':
                    if session['role']!='admin' or not self.direct(): self.response(403,{'error':'Organizer access required.'}); return
                    action=payload.get('action')
                    if action=='create': store.create(payload.get('card',{}),expected_event_id=expected)
                    elif action=='release': store.release(self.ident(payload),expected_event_id=expected)
                    elif action=='grade': store.grade(self.ident(payload),payload.get('passed'),payload.get('note'),expected_event_id=expected)
                    elif action=='service': store.configure_service(self.ident(payload),payload.get('service'),expected_event_id=expected)
                    elif action=='schedule': store.arm_schedule(payload.get('codes'),payload.get('spacing'),payload.get('grace'),payload.get('duration'),expected_event_id=expected)
                    elif action=='announce': store.announce(payload.get('message'),expected_event_id=expected)
                    elif action=='settings': store.settings(payload.get('settings',{}),expected_event_id=expected)
                    elif action=='attach': self.attach(payload)
                    else: raise ValueError('Unknown organizer action.')
                else: self.response(404,{'error':'Unknown action.'}); return
                self.response(200,{'ok':True})
            except EventChanged as error: self.response(409,{'error':str(error)})
            except (ValueError,UnicodeDecodeError,KeyError,TypeError) as error: self.response(400,{'error':str(error)[:300]})
            except (OSError,sqlite3.Error): self.response(503,{'error':'Portal storage is unavailable. Contact White Team.'})

        @staticmethod
        def ident(payload):
            value=payload.get('id')
            if isinstance(value,bool) or not isinstance(value,int) or value<=0: raise ValueError('Invalid inject ID.')
            return value

        def attach(self,payload):
            ident=self.ident(payload); event=store.event(expected_event_id=payload['event_id'])
            name=payload.get('name','')
            import re
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',name): raise ValueError('Use a simple attachment filename with no spaces or paths.')
            content=base64.b64decode(payload.get('content',''),validate=True)
            if not 0<len(content)<=2*1024*1024: raise ValueError('Attachments must be 1 byte to 2 MB.')
            with store.db() as db:
                card=store._card(db,ident,event)
                if card['released_at'] is not None: raise ValueError('Attach resources before releasing the card.')
                total=db.execute('SELECT COUNT(*) FROM attachments WHERE inject_id=?',(ident,)).fetchone()[0]
                if total>=10: raise ValueError('Maximum ten attachments per card.')
                folder=files/'attachments'; folder.mkdir(mode=0o700,exist_ok=True)
                stored=secrets.token_hex(16); target=folder/stored
                try:
                    with target.open('xb') as stream: stream.write(content)
                    target.chmod(0o600)
                    db.execute('INSERT INTO attachments(inject_id,name,stored_name) VALUES(?,?,?)',(ident,name,stored))
                    store.log(db,event['id'],'admin','attach',card['code']+': '+name,time.time())
                except Exception:
                    target.unlink(missing_ok=True); raise

    return PortalHTTPServer((host,port),Handler)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['serve','init','passwords','seed'],nargs='?',default='serve')
    parser.add_argument('--root',type=Path,default=BASE/'portal-state')
    parser.add_argument('--scoring',type=Path,default=BASE/'state/results.sqlite3')
    parser.add_argument('--config',type=Path,default=BASE/'config.json')
    parser.add_argument('--port',type=int,default=8767)
    args=parser.parse_args(); root=args.root
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    store=PortalStore(root/'portal.sqlite3',args.scoring,args.config)
    auth=root/'auth.json'
    if args.command=='init':
        if auth.exists(): raise SystemExit('Existing portal credentials preserved. Use passwords to rotate intentionally.')
        team=secrets.token_urlsafe(24); admin=secrets.token_urlsafe(24)
        write_auth(auth,team,admin)
        secret=root/'INITIAL-PORTAL-CREDENTIALS.txt'
        with secret.open('x',encoding='utf-8') as stream: stream.write(f'Team username: team\nTeam password: {team}\nOrganizer username: admin\nOrganizer password: {admin}\n')
        secret.chmod(0o600)
        print('Portal initialized. Credentials are in the protected portal-state/INITIAL-PORTAL-CREDENTIALS.txt file; no passwords were printed.')
    elif args.command=='passwords':
        team=getpass.getpass('New team password: '); admin=getpass.getpass('New organizer password: ')
        write_auth(auth,team,admin)
        print('Passwords updated; existing sessions are invalidated.')
    elif args.command=='seed':
        source=BASE/'portal-injects.json'; cards=json.loads(source.read_text())
        for card in cards:
            try: store.create(card)
            except ValueError as error:
                if 'already exists' not in str(error): raise
        print(f'{len(cards)} organizer-only draft injects staged in the current event. No tasks released.')
    else:
        if not auth.exists(): raise SystemExit('Initialize credentials before serving.')
        server=make_server(store,auth,root/'files',port=args.port)
        print(f'Portal listening on 127.0.0.1:{args.port}',flush=True)
        server.serve_forever()


if __name__=='__main__': main()
