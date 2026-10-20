"""Assemble disposable test/package contexts from this source tree only.

This copies files locally. It never installs anything or contacts lab machines.
"""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def tree(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True)


def prepare(kind, output):
    output = output.resolve()
    if output.exists():
        raise ValueError('Output already exists; use a new directory to avoid stale files')
    if output == ROOT or output in ROOT.parents:
        raise ValueError('Output must not contain the source repository')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT/'.build'):
        raise ValueError('Inside this repository, output must be under .build/ to protect source inputs')
    output.mkdir(parents=True)
    if kind == 'score01':
        tree(ROOT/'competition-code/score01', output)
        for category in ('installation-and-event-setup', 'packaging', 'operations', 'verification', 'tests'):
            tree(ROOT/'preparation'/category/'score01', output)
        config = ROOT/'competition-code/running-configs/score01'
        for name in ('config.example.json', 'portal-injects.example.json', 'portal-injects.json',
                     'summit-shop01.crt', 'mail01-webmail-trust.pem'):
            shutil.copyfile(config/name, output/name)
        for p in config.rglob('*.service'):
            shutil.copyfile(p, output/p.name)
        for p in config.rglob('*.timer'):
            shutil.copyfile(p, output/p.name)
        for ext in ('md', 'docx'):
            shutil.copyfile(ROOT/f'competition-code/materials/PARTICIPANT-README.{ext}', output/f'README.{ext}')
        shutil.copyfile(ROOT/'docs/legacy-score01/PORTAL-README.md', output/'PORTAL-README.md')
    elif kind == 'panel':
        runtime = ROOT/'competition-code/red-team'
        tree(runtime/'controller', output/'payload/controller')
        tree(runtime/'caldera', output/'payload/caldera')
        units = ROOT/'competition-code/running-configs/red01/deployed/etc/systemd/system'
        tree(units, output/'payload/systemd')
        tree(ROOT/'preparation/packaging/red-team', output)
        tree(ROOT/'preparation/panel-context', output)
        tree(ROOT/'third-party/caldera-test-support', output/'upstream-test-support')
        shutil.copyfile(ROOT/'docs/PANEL-PACKAGING.md', output/'README.md')
        shutil.copyfile(ROOT/'docs/VALIDATION.md', output/'REVIEW.md')
    else:
        raise ValueError('Unknown workspace: '+kind)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('score01', 'panel'))
    parser.add_argument('--output', type=Path, help='New directory; defaults to .build/<kind>')
    args = parser.parse_args()
    print(prepare(args.kind, args.output or ROOT/'.build'/args.kind))
