#!/usr/bin/env python3
"""Fingerprint-specific system CA check; retain actual corporate anchors."""
import argparse
import base64
import hashlib
from pathlib import Path
import re
import tempfile
from policy import run

ISSUES=(11,)


TRAINING_CA_SHA256='27a1a39bd003d5fc0494e82066570ef74206d4da486c39d946faaba239ba5ebe'


def certificate_fingerprints(bundle):
    if not isinstance(bundle,str): return None
    certificates=re.findall(r'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----',bundle,re.S)
    if not certificates: return None
    try:
        decoded=[base64.b64decode(re.sub(r'\s','',c),validate=True) for c in certificates]
        if any(not c for c in decoded): return None
        return {hashlib.sha256(c).hexdigest() for c in decoded}
    except (ValueError,TypeError): return None


def certificate_absent(bundle,fingerprint):
    if not re.fullmatch('[a-f0-9]{64}',fingerprint or ''): return False
    fingerprints=certificate_fingerprints(bundle)
    return fingerprints is not None and fingerprint not in fingerprints


def current_fingerprints():
    try:
        # Extract current trust into private temporary output; anchors are untouched.
        with tempfile.TemporaryDirectory(prefix='summit-trust-probe-') as temporary:
            bundle=Path(temporary)/'anchors.pem'
            p=run(['trust','extract','--filter=ca-anchors','--format=pem-bundle',str(bundle)])
            if p is None or p.returncode!=0: return None
            return certificate_fingerprints(bundle.read_text())
    except (OSError,UnicodeError,ValueError,TypeError): return None


def check(issue):
    if issue!=11: return False
    fingerprints=current_fingerprints()
    return fingerprints is not None and TRAINING_CA_SHA256 not in fingerprints


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--issue',type=int,choices=ISSUES,required=True)
    args=parser.parse_args()
    print('PASS' if check(args.issue) else 'FAIL')
