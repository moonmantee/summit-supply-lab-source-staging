"""Build a secret-free, self-contained score01 deployment package."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

base=Path(__file__).resolve().parent
out=base/'team-portal-package'
out.mkdir(exist_ok=False)
names=['scorer.py','shop_probe.py','lifecycle.py','reporting.py','inject_services.py','arm_inject_schedule.py','portal_scoreboard.py','prepare_inject_resources.py','scoreboard.css','scoreboard.js','portal_server.py','portal_store.py','portal-injects.json','portal-install.sh','summit-team-portal.service','PORTAL-README.md','portal-web/index.html','portal-web/app.js','portal-web/style.css']
for name in names:
    dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True)
    if name.endswith(('.py','.sh','.service','.md','.json','.js','.css','.html')):
        dst.write_text((base/name).read_text(encoding='utf-8-sig'),encoding='utf-8',newline='\n')
    else: shutil.copy2(base/name,dst)
for name in ['inject-resources/shipping-policy.txt','inject-resources/health.json']:
    dst=out/name; dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_bytes((base/name).read_bytes())
(out/'README.md').write_text((base/'README.md').read_text(encoding='utf-8-sig'),encoding='utf-8',newline='\n')
shutil.copy2(base/'README.docx',out/'README.docx')
manifest={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json'}
(out/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
archive=base/'team-portal-package.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zip:
    for name in [*manifest,'SHA256SUMS.json']:zip.write(out/name,'team-portal-package/'+name)
print(f'Packaged {len(manifest)} files. No portal-state, databases, or generated credentials included.')
print(archive)
