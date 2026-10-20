"""Build a manifest from reviewed source files and a public predecessor inventory."""
import hashlib
import json
import pathlib
import shutil
ROOT=pathlib.Path(__file__).resolve().parent
baseline=json.loads((ROOT/'reference/predecessor-manifest.json').read_text(encoding='utf-8-sig'))
runtime=json.loads((ROOT/'reference/runtime-dependencies.json').read_text(encoding='utf-8-sig'))
baseline.update(runtime)
release=ROOT/'release';release.mkdir(exist_ok=True)
build_dist=ROOT/'build/plugins/magma/dist'
dist=release/('magma-dist-'+hashlib.sha256((build_dist/'index.html').read_bytes()).hexdigest()[:12])
shutil.copytree(ROOT/'build/plugins/magma/dist',dist,dirs_exist_ok=True)
files=[]
def add(path,destination):
    files.append(dict(source=path.relative_to(ROOT).as_posix(),destination=destination,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),predecessor=baseline.get(destination)))
for name in ['fixture_coordinator.py','fixture_control.py','panel_catalog.py','panel_store.py','panel_service.py','panel_socket.py','panel_client.py']:
    add(ROOT/'payload/controller'/name,'/opt/summit-caldera-fixtures/'+name)
add(ROOT/'payload/caldera/launch.py','/opt/summit-caldera/launch.py')
add(ROOT/'payload/systemd/summit-caldera-coordinator.service','/etc/systemd/system/summit-caldera-coordinator.service')
add(ROOT/'payload/caldera/plugins/magma/src/components/core/Navigation.vue','/opt/summit-caldera/plugins/magma/src/components/core/Navigation.vue')
plugin=ROOT/'payload/caldera/plugins/ccdc'
for path in plugin.rglob('*'):
    if path.is_file() and path.suffix in ('.py','.vue','.js'):add(path,'/opt/summit-caldera/plugins/ccdc/'+path.relative_to(plugin).as_posix())
for path in dist.rglob('*'):
    if path.is_file():add(path,'/opt/summit-caldera/plugins/magma/dist/'+path.relative_to(dist).as_posix())
destinations={item['destination'] for item in files}
dependencies=[dict(destination=path,sha256=sha) for path,sha in baseline.items() if path not in destinations and (path.startswith('/opt/summit-caldera-fixtures/') or path=='/opt/summit-caldera/stage_policy.py' or path in runtime)]
support=[dict(source=name,sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()) for name in ('install_panel.py','rollback_panel.py','verify_panel.py','README.md','REVIEW.md')]
manifest=dict(version=1,files=files,dependencies=dependencies,support=support)
data=(json.dumps(manifest,indent=2)+'\n').encode();(ROOT/'release-manifest.json').write_bytes(data)
print(json.dumps(dict(files=len(files),dependencies=len(dependencies),manifest_sha256=hashlib.sha256(data).hexdigest())))
