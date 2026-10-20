import json
from pathlib import Path

root=Path(__file__).parent
path=root/'competition-manifest.json'
manifest=json.loads(path.read_text(encoding='utf-8-sig'))
for issue in manifest['issues']:
    if issue['id']==20:
        issue['planted_state']='Domain competitor administration permits sudo password bypass'
        issue['repair']='Both approved domain competitors require authentication for all authorized sudo operations; no effective NOPASSWD alternate. Preserve domain administration and the separate local fallback.'
    if issue['id']==21:
        issue['planted_state']='Domain competitor sudo credential caching exceeds policy'
        issue['repair']='Effective sudo timestamp_timeout between 0 and 5 minutes for both approved domain competitors, including per-context overrides. Preserve the separate local fallback.'
    if issue['id'] in (20,21):
        issue.pop('target_local_account',None)
        issue['target_domain_accounts']=['alex.admin@corp.summit.test','taylor.admin@corp.summit.test']
        issue['implementation_status']='probe-unit-tested-after-domain-migration'
manifest['competitor_domain_group']='linux-workstation-admins@corp.summit.test'
manifest['competitor_fallback_account']='competitor-recovery'
path.write_text(json.dumps(manifest,indent=2)+'\n')
print('Updated sudo targets; count and points unchanged.')
