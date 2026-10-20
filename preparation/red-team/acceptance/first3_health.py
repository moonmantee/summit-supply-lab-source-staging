"""Read-only existing scored storefront probe; never changes scoring results."""
import json,pathlib,sys
sys.path.insert(0,'/home/jwang/summit-scoring')
import scorer
config=json.loads(pathlib.Path('/home/jwang/summit-scoring/config.json').read_text())
services=[item for item in scorer.resolve_services(config) if item['id']=='shop01-https']
assert len(services)==1,'Exact scored storefront not found'
status,reason=scorer.run_probe(services[0])
print(json.dumps({'service':'shop01-https','status':status,'reason':reason}))
if status!='PASS':sys.exit(2)
