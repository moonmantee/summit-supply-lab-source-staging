#!/usr/bin/env python3
"""Deploy approved forty-check encrypted Aeacus config with private rollback."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import build_config
from acceptance_helpers import require_state, scenario_fingerprint
from release_helpers import require_rehearsal, require_report, cutover_transaction, require_user_viewer, private_phocus, wait_scoring_report
from validate_results import collect

SOURCE=Path(__file__).resolve().parent
RUNTIME=Path('/opt/summit-shop01')
ENGINE=Path('/opt/aeacus')
DIAGNOSTICS=('shop01-baseline.json','shop01-probe-after.json','shop01-defense-core-rehearsal.jsonl',
 'shop01-permissions-rehearsal.jsonl','shop01-ssh-rehearsal.jsonl','shop01-firewall-baseline.json',
 'shop01-package-preparation.txt','shop01-probe-validation-report.html','shop01-combined-rehearsal.json',
 'shop01-persistence-rehearsal.jsonl','shop01-firewall-diagnostic.json','shop01-firewall-rehearsal.jsonl',
 'shop01-apache-rehearsal.jsonl','shop01-pam-rehearsal.jsonl','shop01-users-rehearsal.jsonl',
 'shop01-audit-rehearsal.jsonl','shop01-probe-before.json','shop01-firewall-remote.jsonl',
 'shop01-probe-validation.json','shop01-firewall-phase.json','shop01-firewall-ack.json')
BACKUP=None


def call(args,cwd=None):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=240)
    with (BACKUP/'commands.log').open('a') as f: f.write(repr(args)+'\n'+p.stdout+p.stderr+'\n')
    if p.returncode: raise RuntimeError('Command failed: '+args[0]+'; private commands.log')
    return p.stdout


def install(source,target,mode):
    p=Path(target)
    if p.is_symlink(): raise RuntimeError('Refusing symlink: '+str(p))
    shutil.copyfile(source,p); os.chown(p,0,0); p.chmod(mode)


def prepare_candidate(config):
    # Prove check/readme/score/encrypt in isolation while the old scorer runs.
    candidate=BACKUP/'candidate'; candidate.mkdir(mode=0o700)
    shutil.copytree(ENGINE/'assets',candidate/'assets')
    (candidate/'assets/previous.txt').write_text('0')
    install(ENGINE/'TeamID.txt',candidate/'TeamID.txt',0o600)
    try:
        (RUNTIME/'probes').mkdir(parents=True,mode=0o700)
        RUNTIME.chmod(0o700)
        for p in (SOURCE/'probes').glob('*.py'):
            if not p.name.startswith('test_'): install(p,RUNTIME/'probes'/p.name,0o600)
        for name in ('competition-manifest.json','validate_results.py','acceptance_helpers.py','release_helpers.py','verify-release.py'):
            install(SOURCE/name,RUNTIME/name,0o600)
        (candidate/'scoring.conf').write_text(config)
        install(SOURCE/'ReadMe.conf',candidate/'ReadMe.conf',0o600)
        for command in ('check','readme','score','encrypt'):
            # v2.1.1 genReadMe opens ReadMe.conf relative to cwd, despite --dir.
            # Keep all native subcommands inside the isolated candidate.
            call([str(ENGINE/'aeacus'),'--dir',str(candidate)+'/',command],cwd=candidate)
        require_report((candidate/'assets/ScoringReport.html').read_text())
        encrypted=candidate/'scoring.dat'
        if not encrypted.is_file() or encrypted.stat().st_size<100: raise RuntimeError('Encrypted config missing')
        encrypted.chmod(0o600)
        (candidate/'scoring.conf').unlink()
        # Native aeacus check/score require plaintext; Phocus loads scoring.dat.
        private_phocus(candidate,ENGINE/'phocus')
        print('Isolated encrypted forty-check Phocus candidate verified at 0/100.',flush=True)
    except BaseException:
        if RUNTIME.exists() and not RUNTIME.is_symlink(): shutil.rmtree(RUNTIME)
        raise
    return candidate


def rollback():
    call(['systemctl','stop','summit-aeacus'])
    # The only newly-created runtime tree; refuse to follow a substituted link.
    if RUNTIME.is_symlink(): raise RuntimeError('Runtime replaced by symlink')
    if RUNTIME.exists(): shutil.rmtree(RUNTIME)
    for name in ('scoring.conf','scoring.dat','ReadMe.conf'):
        p=ENGINE/name
        if p.exists(): p.unlink()
    call(['tar','--acls','--xattrs','--numeric-owner','-xpf',str(BACKUP/'engine.tar'),'-C','/'])
    call(['systemctl','start','summit-aeacus'])
    call(['systemctl','is-active','--quiet','summit-aeacus'])


def main():
    global BACKUP
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='shop01': raise RuntimeError('Run with sudo on shop01')
    os.umask(0o077)
    if SOURCE.stat().st_uid!=0 or SOURCE.stat().st_mode & 0o077:
        raise RuntimeError('Use deploy-scoring.sh for private execution')
    if RUNTIME.exists() or RUNTIME.is_symlink(): raise RuntimeError('Scoring runtime already exists; refusing replacement')
    import re
    proof=json.loads(Path('/home/jwang/shop01-combined-rehearsal.json').read_text())
    rehearsal=Path(proof['backup'])
    if (str(rehearsal.parent)!='/var/backups' or not re.fullmatch(r'summit-shop01-all-[A-Za-z0-9_]+',rehearsal.name)
        or rehearsal.is_symlink() or rehearsal.stat().st_uid!=0 or rehearsal.stat().st_mode & 0o077):
        raise RuntimeError('Unsafe combined acceptance evidence')
    require_rehearsal({'repaired':json.loads((rehearsal/'combined-repaired.json').read_text()),
                       'restored':json.loads((rehearsal/'restored-planted.json').read_text())})
    if json.loads((rehearsal/'source-hashes.json').read_text())!=scenario_fingerprint(SOURCE):
        raise RuntimeError('Scoring changed since combined proof; rerun rehearse-all.sh')
    require_state(collect(SOURCE),False)
    manifest=json.loads((SOURCE/'competition-manifest.json').read_text())
    config=build_config.render(manifest)
    BACKUP=Path(tempfile.mkdtemp(prefix='summit-shop01-production-',dir='/var/backups'))
    print('Private production rollback: '+str(BACKUP),flush=True)
    for unit in ('summit-aeacus','ssh','sssd','apache2'):
        call(['systemctl','is-active','--quiet',unit])
    import pwd
    require_user_viewer(call,pwd.getpwnam('jwang').pw_uid)
    if call(['systemctl','show','summit-aeacus','-p','User','--value']).strip()!='root':
        raise RuntimeError('Scorer must use root')
    if call(['systemctl','show','summit-aeacus','-p','WorkingDirectory','--value']).strip()!=str(ENGINE):
        raise RuntimeError('Unexpected scorer working directory')
    def snapshot():
        call(['tar','--acls','--xattrs','--numeric-owner','-cpf',str(BACKUP/'engine.tar'),'-C','/','opt/aeacus'])
        (BACKUP/'ready').write_text('Original production engine captured\n')
    def interrupted(signum,frame): raise RuntimeError('Interrupted '+str(signum))
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    def apply(candidate):
        install(candidate/'scoring.dat',ENGINE/'scoring.dat',0o600)
        install(candidate/'ReadMe.conf',ENGINE/'ReadMe.conf',0o600)
        install(candidate/'assets/ReadMe.html',ENGINE/'assets/ReadMe.html',0o644)
        if (ENGINE/'scoring.conf').exists(): (ENGINE/'scoring.conf').unlink()
        # Remove the pre-cutover report so the encrypted service must create it.
        report=ENGINE/'assets/ScoringReport.html'; report.unlink()
        call(['systemctl','start','summit-aeacus'])
        wait_scoring_report(report,lambda: subprocess.run(['systemctl','is-active','--quiet','summit-aeacus']).returncode==0,timeout=180)
        call(['systemctl','is-active','--quiet','summit-aeacus'])
        require_state(collect(RUNTIME),False)
        for p in (report,ENGINE/'assets/ReadMe.html'): p.chmod(0o644)
        # The report viewer and existing shortcuts continue using these paths.
        if not (ENGINE/'assets/ReadMe.html').is_file(): raise RuntimeError('Participant ReadMe missing')
    def cleanup():
        if RUNTIME.is_symlink(): raise RuntimeError('Runtime replaced by symlink')
        if RUNTIME.exists(): shutil.rmtree(RUNTIME)
    try:
        cutover_transaction(prepare=lambda:prepare_candidate(config),
                            stop=lambda:call(['systemctl','stop','summit-aeacus']),
                            snapshot=snapshot,apply=apply,rollback=rollback,
                            resume=lambda:call(['systemctl','start','summit-aeacus']),cleanup=cleanup)
    except BaseException:
        print('Cutover stopped; original scorer restoration attempted. Recovery: '+str(BACKUP),flush=True)
        raise
    (BACKUP/'installed.json').write_text(json.dumps({'count':40,'total_points':100,'points':0,'encrypted':True})+'\n')
    # Archive organizer-only staging after successful cutover. Never export private credentials.
    organizer=BACKUP/'organizer'; organizer.mkdir(mode=0o700)
    staging=Path('/home/jwang/shop01-setup')
    if staging.is_symlink(): raise RuntimeError('Unexpected staging symlink')
    shutil.move(str(staging),str(organizer/'shop01-setup'))
    for name in DIAGNOSTICS:
        p=Path('/home/jwang')/name
        if p.is_symlink(): raise RuntimeError('Unexpected diagnostic symlink: '+name)
        if p.is_file(): shutil.move(str(p),str(organizer/name))
    call(['chown','-R','root:root',str(organizer)])
    for p in organizer.rglob('*'):
        if not p.is_symlink(): p.chmod(0o700 if p.is_dir() else 0o600)
    call(['python3',str(RUNTIME/'verify-release.py')])
    print('Production encrypted Aeacus deployed: forty checks, 100 possible points, current score 0.',flush=True)
    print('Organizer staging archived privately. Post-reboot/domain/external service verification remains.',flush=True)


if __name__=='__main__': main()
