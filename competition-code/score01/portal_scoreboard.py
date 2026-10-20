"""Reuse the existing scorer dashboard, with authenticated read-only access."""
from contextlib import closing
import re
import sqlite3
import reporting
from lifecycle import get_current_event


def page(store,history=False):
    state=store.scoring()
    if not state['available']: raise OSError('Scorer unavailable')
    services=[dict(s,id=s['service_id']) for s in state['services']]
    with closing(sqlite3.connect(store.scoring_path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        event=get_current_event(db)
        content=reporting.render_event_history(db,services,event.id) if history else reporting._status_page(db,services,event,'')
    # Team view never contains organizer controls or the private control token.
    content=re.sub(r'<section class="panel control-panel".*?</section>','',content,flags=re.S)
    content=re.sub(r'<meta name="summit-control-token"[^>]*>','',content)
    content=re.sub(r'<a class="event-link[^\"]*" href="history-event-\d+\.html">.*?</a>','',content,flags=re.S)
    return content.encode('utf-8')
