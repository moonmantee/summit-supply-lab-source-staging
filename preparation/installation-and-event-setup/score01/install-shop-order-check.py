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


if __name__ == '__main__':
    import base64
    import zlib
    try:
        raise SystemExit(main(zlib.decompress(base64.b64decode('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')).decode()))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))

