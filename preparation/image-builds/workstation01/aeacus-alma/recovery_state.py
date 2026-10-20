"""Resume preparation without replacing original records or archived RPMs."""
from pathlib import Path


def ensure_directory(path,owner=None):
    path=Path(path)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError('Unsafe recovery directory: '+str(path))
    if path.exists() and owner is not None:
        s=path.stat()
        if s.st_uid!=owner or s.st_mode & 0o077:
            raise ValueError('Recovery directory ownership/permissions differ: '+str(path))
    path.mkdir(mode=0o700,exist_ok=True)


def preserve_file(path,data,owner=None):
    path=Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Unsafe recovery file: '+str(path))
    if path.exists():
        if owner is not None and path.stat().st_uid!=owner:
            raise ValueError('Recovery file owner differs: '+str(path))
        if path.read_bytes()!=data:
            raise ValueError('Saved recovery data differs; refusing replacement: '+str(path))
        return
    with path.open('xb') as f:
        f.write(data)
    path.chmod(0o600)
