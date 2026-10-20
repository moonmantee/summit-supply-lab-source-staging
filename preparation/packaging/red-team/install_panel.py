"""Guarded local red01 installation. No credentials leave this host."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import uuid

CONF=pathlib.Path('/etc/summit-caldera-fixtures/runtime/config.json')
UNITS=['summit-caldera-coordinator','summit-caldera-contact','summit-caldera']


def regular_bytes(path):
    flags=os.O_RDONLY|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0)
    with os.fdopen(os.open(path,flags),'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):raise ValueError('Nonregular file denied: '+str(path))
        return stream.read(),info


def digest(path): return hashlib.sha256(regular_bytes(path)[0]).hexdigest()


def current_digest(path):
    try:return digest(path)
    except FileNotFoundError:return None


def credential_fingerprint(credentials_json,runtime_yaml):
    import yaml
    records=json.loads(credentials_json.read_text())
    runtime=yaml.safe_load(runtime_yaml.read_text())
    auth={key:runtime.get(key) for key in ('users','api_key_red','api_key_blue','crypt_salt','encryption_key')}
    return hashlib.sha256(json.dumps({'records':records,'auth':auth},sort_keys=True).encode()).hexdigest()


def safe_path(root, relative):
    relative=pathlib.PurePosixPath(relative)
    if '..' in relative.parts: raise ValueError('Path traversal denied')
    path=root.joinpath(*[p for p in relative.parts if p!='/'])
    current=path
    while current!=root:
        if current.is_symlink(): raise ValueError('Symlink publication denied')
        if root not in current.parents: raise ValueError('Path escapes root')
        current=current.parent
    return path


def permitted(destination):
    return (destination=='/etc/systemd/system/summit-caldera-coordinator.service'
        or destination=='/opt/summit-caldera/launch.py'
        or destination=='/opt/summit-caldera/plugins/magma/src/components/core/Navigation.vue'
        or destination.startswith('/opt/summit-caldera/plugins/ccdc/')
        or destination.startswith('/opt/summit-caldera/plugins/magma/dist/')
        or destination.startswith('/opt/summit-caldera-fixtures/') and pathlib.PurePosixPath(destination).parent==pathlib.PurePosixPath('/opt/summit-caldera-fixtures') and destination.endswith('.py'))


def validate_package(package,manifest_hash,filesystem=pathlib.Path('/'),hostname=None):
    if (hostname or socket.gethostname()).split('.')[0]!='red01': raise ValueError('This package is for red01 only')
    package=package.resolve()
    if digest(package/'release-manifest.json')!=manifest_hash: raise ValueError('Manifest hash mismatch')
    manifest=json.loads((package/'release-manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['version']!=1 or len(manifest['files'])>512: raise ValueError('Unsupported package')
    destinations=set()
    for item in manifest['files']:
        if not permitted(item['destination']) or item['destination'] in destinations: raise ValueError('Invalid installation destination')
        destinations.add(item['destination'])
        source=safe_path(package,item['source'])
        if not source.is_file() or digest(source)!=item['sha256']: raise ValueError('Payload hash mismatch')
        path=safe_path(filesystem,item['destination'])
        actual=current_digest(path)
        if actual!=item['predecessor']: raise ValueError('Predecessor changed: '+item['destination'])
    for item in manifest.get('support',[]):
        if digest(safe_path(package,item['source']))!=item['sha256']: raise ValueError('Support file hash mismatch')
    for item in manifest.get('dependencies',[]):
        if digest(safe_path(filesystem,item['destination']))!=item['sha256']: raise ValueError('Controller dependency changed')
    if shutil.disk_usage(filesystem).free<256*1024*1024: raise ValueError('At least 256 MiB free space required')
    return manifest


def backup_files(manifest,backup,filesystem=pathlib.Path('/')):
    backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    records=[]
    for index,item in enumerate(manifest['files']):
        path=safe_path(filesystem,item['destination']);actual=current_digest(path)
        if actual!=item['predecessor']:raise ValueError('Concurrent file replacement preserved')
        record={'destination':item['destination'],'stored':str(index),'existed':actual is not None}
        parents=[];parent=path.parent
        while parent!=filesystem and not parent.exists():parents.append(str(parent.relative_to(filesystem)));parent=parent.parent
        record['new_directories']=parents
        if actual is not None:
            data,info=regular_bytes(path)
            if hashlib.sha256(data).hexdigest()!=actual:raise ValueError('Concurrent file replacement preserved')
            record.update(mode=info.st_mode&0o777,uid=info.st_uid,gid=info.st_gid,sha256=actual)
            (backup/str(index)).write_bytes(data);os.chmod(backup/str(index),0o600)
        records.append(record)
    (backup/'files.json').write_text(json.dumps(records));os.chmod(backup/'files.json',0o600)


def atomic_bytes(path,data,mode=0o644,owner=None):
    path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.ccdc-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,mode)
        if owner is not None: os.chown(temporary,*owner)
        os.replace(temporary,path)
        if os.name=='posix':
            fd=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
    finally:temporary.unlink(missing_ok=True)


def publish_files(manifest,package,filesystem=pathlib.Path('/')):
    for item in manifest['files']:
        path=safe_path(filesystem,item['destination'])
        if current_digest(path)!=item['predecessor']: raise ValueError('Concurrent file replacement preserved')
        data,_=regular_bytes(safe_path(package,item['source']))
        if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Payload changed after preflight')
        atomic_bytes(path,data)


def restore_files(manifest,backup,filesystem=pathlib.Path('/')):
    records=json.loads((backup/'files.json').read_text())
    allowed={item['destination']:{item['sha256'],item['predecessor']} for item in manifest['files']}
    # Validate the entire restore before touching any replacement.
    for record in records:
        path=safe_path(filesystem,record['destination'])
        actual=current_digest(path)
        if actual not in allowed[record['destination']]: raise ValueError('Unknown replacement preserved: '+record['destination'])
        if record['existed'] and digest(backup/record['stored'])!=record['sha256']: raise ValueError('Backup hash mismatch')
    for record in records:
        path=safe_path(filesystem,record['destination'])
        if record['existed']:
            atomic_bytes(path,(backup/record['stored']).read_bytes(),record['mode'],(record['uid'],record['gid']) if os.name=='posix' else None)
        else:path.unlink(missing_ok=True)
    directories={name for record in records for name in record.get('new_directories',[])}
    for name in sorted(directories,key=lambda p:len(pathlib.Path(p).parts),reverse=True):
        try:safe_path(filesystem,name).rmdir()
        except OSError:pass  # Preserve concurrent contents and already-removed dirs.


def run(*args): return subprocess.run(args,check=True,capture_output=True,text=True)


def read_current(config):
    path=pathlib.Path(config['state'])
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        current=db.execute('SELECT * FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
        if not current or current['state']!='DISARMED': raise ValueError('Installation requires an existing DISARMED exercise')
        if db.execute("SELECT 1 FROM dispatch WHERE outcome IN ('DISPATCHED','ACCEPTED')").fetchone(): raise ValueError('Unresolved dispatch must be reconciled before installation')
    if json.loads(pathlib.Path(config['scenario']).read_text()): raise ValueError('Installation requires an empty current schedule')
    return dict(current)


def snapshot_database(source,destination):
    with sqlite3.connect(source) as src,sqlite3.connect(destination) as dst:src.backup(dst)
    os.chmod(destination,0o600)


def migrate(config):
    sys.path.insert(0,'/opt/summit-caldera-fixtures')
    from panel_store import PanelStore
    from panel_catalog import build_catalog,validate_profile
    from legacy.state import Store
    from fixture_coordinator import scoring
    imports={}
    for path in pathlib.Path('/opt/summit-caldera-fixtures/profiles').glob('*.json'):
        name=path.stem;duration=14400 if name.startswith(('first4h','hour4')) else 10800 if name.startswith('first3h') else 12600
        imports[name]=dict(name={'empty':'Empty','first3h-all':'First three hours','first4h-all':'First four hours'}.get(name,name),duration=duration,events=json.loads(path.read_text()))
    for name,count in [('first3h-all',102),('first4h-all',110)]:
        validate_profile(imports[name],build_catalog(config['guests'],config['guests']))
        if len(imports[name]['events'])!=count: raise ValueError('Accepted template count changed')
    store=Store(config['state']);panel=PanelStore(store)
    panel.initialize([],imports)
    with store.transaction() as tx: panel.load_snapshot(tx,'empty',1,scoring(config['scoring_export'])['id'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256',required=True);parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0: raise ValueError('Run locally with sudo on red01')
    package=pathlib.Path(__file__).resolve().parent
    manifest=validate_package(package,args.manifest_sha256)
    config=json.loads(CONF.read_text());read_current(config)
    if shutil.disk_usage(pathlib.Path(config['state']).parent).free<256*1024*1024:raise ValueError('At least 256 MiB free on state filesystem required')
    # Validate imported schedules and freshness without mutating the live DB.
    sys.path.insert(0,str(package/'payload/controller'))
    from panel_catalog import build_catalog,validate_profile
    from fixture_coordinator import scoring
    for name,duration,count in [('first3h-all',10800,102),('first4h-all',14400,110)]:
        events=json.loads((pathlib.Path('/opt/summit-caldera-fixtures/profiles')/(name+'.json')).read_text())
        validate_profile(dict(name=name,duration=duration,events=events),build_catalog(config['guests'],config['guests']))
        if len(events)!=count: raise ValueError('Accepted template count mismatch')
    scoring(config['scoring_export'])
    if args.check: print(json.dumps({'check':'PASS','host':'red01','files':len(manifest['files'])}));return
    backup=pathlib.Path('/var/backups/ccdc-panel')/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    credentials=[pathlib.Path('/etc/summit-caldera/credentials.json'),pathlib.Path('/etc/summit-caldera/runtime/summit.yml')]
    original_credentials=credential_fingerprint(*credentials)
    for unit in UNITS: run('systemctl','stop',unit)
    try:
        read_current(config);backup_files(manifest,backup)
        snapshot_database(config['state'],backup/'state-before.sqlite3')
        info=pathlib.Path(config['state']).stat()
        (backup/'deployment.json').write_text(json.dumps(dict(manifest=manifest,config_state=config['state'],db_uid=info.st_uid,db_gid=info.st_gid,db_mode=info.st_mode&0o777)))
        publish_files(manifest,package)
        migrate(config)
        if credential_fingerprint(*credentials)!=original_credentials: raise ValueError('Credential record changed')
        run('systemctl','daemon-reload')
        for unit in reversed(UNITS): run('systemctl','start',unit)
        result=run('/opt/summit-caldera/.venv/bin/python',str(package/'verify_panel.py'))
        receipt=json.loads(result.stdout)
        if credential_fingerprint(*credentials)!=original_credentials: raise ValueError('Credential record changed')
        (backup/'receipt.json').write_text(json.dumps(receipt));os.chmod(backup/'receipt.json',0o600)
        print(json.dumps({'installed':'PASS','backup':str(backup),'verification':receipt}))
    except Exception:
        if (backup/'deployment.json').exists():
            from rollback_panel import rollback
            rollback(backup,automatic=True)
        else:
            for unit in reversed(UNITS): run('systemctl','start',unit)
        raise


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('CCDC panel installation stopped: '+str(error),file=sys.stderr);sys.exit(1)
