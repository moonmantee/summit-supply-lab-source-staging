"""Arm the user-selected schedule without starting the competition."""
from pathlib import Path
from portal_store import PortalStore
BASE=Path(__file__).resolve().parent
store=PortalStore(BASE/'portal-state/portal.sqlite3',Path('/home/jwang/summit-scoring/state/results.sqlite3'),Path('/home/jwang/summit-scoring/config.json'))
event=store.event()
store.arm_schedule(['I01','I02','I03','I04','I05','I06'],spacing=1800,grace=1800,duration=14400,expected_event_id=event['id'])
store.enable_event_template(event['id'])
print('Six injects armed for the next Start: every 30 minutes, 30-minute grace, four-hour completion window. Event not started; mail remains blocked pending configuration.')
