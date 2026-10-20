"""Installer template; build_shop_probe_update.py embeds the tested probe."""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HOOK = """        # Summit order/history transaction check.
        if config.get('id') == 'shop01-https' and config.get('probe') == 'https':
            from shop_probe import probe as shop_probe
            return shop_probe(config)
"""
ANCHOR = 'def run_probe(config):\n    try:\n'


def patched(source):
    if HOOK.strip() in source or 'return shop_probe(config)' in source:
        return source
    if source.count(ANCHOR) != 1:
        raise ValueError('Unrecognized scorer.py; no files changed. Supply its source for adaptation.')
    result = source.replace(ANCHOR, ANCHOR+HOOK, 1)
    compile(result, 'scorer.py', 'exec')
    return result


def ctl(*args, check=True):
    return subprocess.run(['systemctl', '--user', *args], check=check,
                          capture_output=True, text=True)


def state(unit):
    result = ctl('show', unit, '--property=ActiveState', '--value', check=False)
    if result.returncode:
        raise RuntimeError('Cannot inspect user services; run as the scorer owner, without sudo.')
    return result.stdout.strip()


def atomic(path, content, mode):
    temporary = path.with_name(path.name+'.shop-update')
    try:
        temporary.write_bytes(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def candidate(config, source):
    import types
    module = types.ModuleType('shop_probe_candidate')
    exec(compile(source, 'shop_probe.py', 'exec'), module.__dict__)
    services = [s for s in config.get('services', []) if s.get('id') == 'shop01-https']
    if len(services) != 1 or services[0].get('probe') != 'https':
        raise ValueError('Expected exactly one shop01-https HTTPS service in config.json')
    return module, services[0]


def main(module_source):
    parser = argparse.ArgumentParser(description='Install Summit order/history scorer check')
    parser.add_argument('--base', type=Path, default=Path.home()/'summit-scoring')
    parser.add_argument('--check', action='store_true', help='Probe live shop only; changes no scorer files')
    parser.add_argument('--rollback', type=Path, help='Restore a backup created by this installer')
    args = parser.parse_args()
    base = args.base.resolve()
    if os.geteuid() == 0:
        raise SystemExit('Run as the scorer owner (normally jwang), without sudo.')
    scorer = base/'scorer.py'
    module_path = base/'shop_probe.py'
    backup = None
    saved = None
    if not args.rollback:
        config = json.loads((base/'config.json').read_text())
        module, service = candidate(config, module_source)
        original = scorer.read_text()
        updated = patched(original)
        if args.check:
            status, reason = module.probe(service)
            print(status+': '+reason)
            return 0 if status == 'PASS' else 1
    else:
        backup = args.rollback.resolve()
        if backup.parent != (base/'backups').resolve() or not backup.name.startswith('shop-order-'):
            raise ValueError('Rollback must name this installer\'s backup in the scorer backups directory')
        saved = json.loads((backup/'manifest.json').read_text())
        if saved['base'] != str(base):
            raise ValueError('Backup belongs to a different scorer directory')

    timer_was_active = state('summit-check.timer') in {'active', 'activating'}
    try:
        ctl('stop', 'summit-check.timer')
        deadline = time.monotonic()+65
        while state('summit-check.service') in {'active', 'activating', 'reloading', 'deactivating'}:
            if time.monotonic() >= deadline:
                raise RuntimeError('Existing scoring round still running; no scorer files changed')
            time.sleep(1)
        if args.rollback:
            for name, info in saved['files'].items():
                target = base/name
                if info['existed']:
                    atomic(target, (backup/name).read_bytes(), info['mode'])
                else:
                    target.unlink(missing_ok=True)
            print('Previous scorer restored. Score database and event history were not changed.')
            return 0

        backup = base/'backups'/dt.datetime.now(dt.timezone.utc).strftime('shop-order-%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True, mode=0o700)
        saved = {'base': str(base), 'files': {}}
        for path in [scorer, module_path]:
            exists = path.exists()
            saved['files'][path.name] = {'existed': exists, 'mode': path.stat().st_mode & 0o777 if exists else 0o600}
            if exists:
                shutil.copy2(path, backup/path.name)
        (backup/'manifest.json').write_text(json.dumps(saved))
        try:
            atomic(module_path, module_source.encode(), saved['files']['shop_probe.py']['mode'])
            atomic(scorer, updated.encode(), saved['files']['scorer.py']['mode'])
            # Import the changed live scorer and verify dispatch, without recording a scoring round.
            sys.path.insert(0, str(base))
            spec = importlib.util.spec_from_file_location('installed_scorer', scorer)
            installed = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(installed)
            import shop_probe
            original_probe = shop_probe.probe
            try:
                shop_probe.probe = lambda config: ('DOWN', 'installer dispatch test')
                if installed.run_probe(service) != ('DOWN', 'installer dispatch test'):
                    raise RuntimeError('Installed scorer did not dispatch the transaction probe')
            finally:
                shop_probe.probe = original_probe
        except BaseException:
            for name, info in saved['files'].items():
                if info['existed']:
                    atomic(base/name, (backup/name).read_bytes(), info['mode'])
                else:
                    (base/name).unlink(missing_ok=True)
            raise
        print('Installed order/history check. Configuration, points and score history preserved.')
        print('Backup: '+str(backup))
        print('Check: python3 '+str(Path(__file__).resolve())+' --check --base '+str(base))
        print('Rollback: python3 '+str(Path(__file__).resolve())+' --base '+str(base)+' --rollback '+str(backup))
        return 0
    finally:
        if timer_was_active:
            ctl('start', 'summit-check.timer')


# PACKAGED_ENTRY_POINT
