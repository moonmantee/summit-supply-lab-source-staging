"""Check source integrity, syntax, local Markdown links and publication exclusions.

This is a focused source/package check, not a claim of a complete security audit.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OMIT = {'.build', '.git', '__pycache__', '.venv', 'node_modules'}
FORBIDDEN = {'.dat', '.zip', '.gz', '.exe', '.dll', '.pyd', '.key', '.pfx', '.p12', '.sqlite', '.sqlite3', '.db'}
PRIVATE = re.compile(r'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----|'
                     r'192\.168\.0\.187|100\.93\.\d+\.\d+|'
                     r'C:[/\\]Users[/\\](?!Public[/\\])[^/\\\s]+[/\\]', re.I)


def source_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not any(part in OMIT for part in p.relative_to(ROOT).parts))


def check():
    errors = []
    counts = {'files': 0, 'python': 0, 'json': 0, 'markdown_links': 0, 'docx': 0}
    files = source_files()
    for p in files:
        name = p.relative_to(ROOT).as_posix()
        counts['files'] += 1
        if p.is_symlink():
            errors.append(name+': symbolic link')
        if p.suffix.lower() in FORBIDDEN:
            errors.append(name+': excluded artifact type')
        if p.suffix == '.docx':
            with zipfile.ZipFile(p) as archive:
                content = '\n'.join(archive.read(n).decode('utf-8') for n in archive.namelist() if n.endswith('.xml'))
            counts['docx'] += 1
        else:
            try:
                content = p.read_text(encoding='utf-8-sig')
            except UnicodeError:
                continue
        if PRIVATE.search(content):
            errors.append(name+': private key, organizer address or personal host path')
        if p.suffix == '.py':
            try:
                ast.parse(content, filename=name)
                counts['python'] += 1
            except SyntaxError as exc:
                errors.append(name+': '+str(exc))
        if p.suffix == '.json':
            try:
                json.loads(content)
                counts['json'] += 1
            except ValueError as exc:
                errors.append(name+': '+str(exc))
        if p.suffix == '.md':
            for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', content):
                target = link.strip('<>').split('#')[0]
                if not target or re.match(r'^[a-zA-Z]+:', target):
                    continue
                counts['markdown_links'] += 1
                dest = (p.parent/unquote(target)).resolve()
                if not dest.is_relative_to(ROOT) or not dest.exists():
                    errors.append(name+': missing or external local link '+target)
    manifest = ROOT/'docs/SOURCE-MANIFEST.json'
    if manifest.exists():
        expected = json.loads(manifest.read_text())
        actual = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in files if p != manifest}
        if actual != expected:
            errors.append('Source manifest mismatch: regenerate after reviewing intended changes')
    if (ROOT/'LICENSE').exists():
        errors.append('Unexpected root LICENSE: original-code license is intentionally undecided')
    return {'counts': counts, 'errors': errors}


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
