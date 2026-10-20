"""Root-owned read-only scoring bridge. Publishes no credentials or score mutations."""
import json
import os
import pathlib
import sqlite3
import tempfile
import time

def export():
    with sqlite3.connect('file:/home/jwang/summit-scoring/state/results.sqlite3?mode=ro',uri=True,timeout=2) as db:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT e.id,e.state FROM competition_events e JOIN scorer_settings s ON e.id=s.current_event_id').fetchone()
    if row is None:raise ValueError('Missing scoring event')
    root=pathlib.Path('/run/summit-caldera-scoring')
    if root.is_symlink() or root.stat().st_uid!=0 or root.stat().st_mode & 0o022:
        raise ValueError('Untrusted scoring export directory')
    fd,name=tempfile.mkstemp(prefix='.state-',dir=root)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump({'id':row[0],'state':row[1],'generated':time.time()},output)
            output.flush();os.fchmod(output.fileno(),0o644);os.fsync(output.fileno())
        os.replace(name,root/'state.json')
    finally:
        if os.path.exists(name):os.unlink(name)

if __name__=='__main__':export()
