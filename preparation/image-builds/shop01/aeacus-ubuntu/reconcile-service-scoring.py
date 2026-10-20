#!/usr/bin/env python3
"""Correct the obsolete independent storefront check without resetting history."""
import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
from service_contract import correct


def main():
    if socket.gethostname().split('.')[0]!='score01': raise RuntimeError('Run on score01')
    base=Path('/home/jwang/summit-scoring'); config=base/'config.json'
    if config.is_symlink(): raise RuntimeError('Unexpected configuration symlink')
    original=config.read_bytes(); data=json.loads(original); proposed=correct(data)
    sys.path.insert(0,str(base))
    import scorer
    service=next(x for x in proposed['services'] if x['id']=='shop01-https')
    status,reason=scorer.run_probe(service)
    if status!='PASS': raise RuntimeError('Proposed trusted HTTPS check failed: '+reason)
    wrong=dict(service,expected=service['expected']+['SUMMIT-ABSENT-CONTROL-MARKER'])
    if scorer.run_probe(wrong)[0]=='PASS': raise RuntimeError('Negative content control unexpectedly passed')
    if proposed==data:
        print('Shop01 HTTPS contract already current; actual TLS/catalog PASS, missing-content control fails.'); return
    backup=base/'backups'/('shop01-catalog-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    (backup/'config.json').write_bytes(original); (backup/'config.json').chmod(0o600)
    def replace(content):
        fd,name=tempfile.mkstemp(prefix='.shop01-contract-',dir=base)
        try:
            with os.fdopen(fd,'wb') as f: f.write(content); f.flush(); os.fsync(f.fileno())
            os.chmod(name,config.stat().st_mode & 0o777)
            os.replace(name,config)
        finally:
            if os.path.exists(name): os.unlink(name)
    replace((json.dumps(proposed,indent=2)+'\n').encode())
    try:
        actual=json.loads(config.read_text())
        if actual!=proposed or scorer.run_probe(next(x for x in actual['services'] if x['id']=='shop01-https'))[0]!='PASS':
            raise RuntimeError('Post-update check failed')
    except BaseException:
        replace(original); raise
    print('Independent shop01 HTTPS: trusted TLS/catalog PASS; missing-content control fails.')
    print('Only obsolete marker/$49 expectation corrected; points, SLA policy, other services and database history retained.')
    print('Private configuration backup: '+str(backup))


if __name__=='__main__': main()
