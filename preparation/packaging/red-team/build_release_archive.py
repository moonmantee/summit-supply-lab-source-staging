"""Archive only the current verified release, sources and Python tests."""
import hashlib
import json
import pathlib
import tarfile
ROOT=pathlib.Path(__file__).resolve().parent
manifest=json.loads((ROOT/'release-manifest.json').read_text())
names={'release-manifest.json','release-verification.json'}
names.update(item['source'] for item in manifest['files']+manifest['support'])
for folder in ('payload','tests','reference/regression'):
    for path in (ROOT/folder).rglob('*'):
        if path.is_file() and path.suffix in ('.py','.json','.vue','.js') and not any(part in ('node_modules','__pycache__','browser') for part in path.relative_to(ROOT).parts):names.add(path.relative_to(ROOT).as_posix())
def mode(info):
    info.mode=0o644
    return info
archive=ROOT/'release-package.tar.gz'
with tarfile.open(archive,'w:gz') as output:
    for name in sorted(names):output.add(ROOT/name,arcname=name,recursive=False,filter=mode)
print(json.dumps(dict(files=len(names),package_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),archive_bytes=archive.stat().st_size)))
