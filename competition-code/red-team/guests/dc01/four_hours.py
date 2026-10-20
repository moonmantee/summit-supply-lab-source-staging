"""Fixed hour-four contract. Existing three-hour manifests retain their limits."""
import math
from fixture_contract import identifiers
from first_three_hours import validate as first3_validate

FAULTS={('shop01','apache'):'business_binary_rename',('sql01','mariadb'):'business_binary_rename',
 ('dc01','dns'):'business_launch_fault',('forum01','web'):'business_launch_fault',
 ('forum01','ftp'):'business_launch_fault',('mail01','smtp'):'business_binary_rename',
 ('mail01','imap'):'business_binary_rename',('mail01','web'):'business_launch_fault'}
ACTIONS=frozenset(FAULTS.values())

def binding(event):
    if any(type(event[k]) is not str for k in ('guest','target','action')):raise ValueError('Invalid hour-four identifiers')
    if FAULTS.get((event['guest'],event['target']))!=event['action']:raise ValueError('Unapproved hour-four action/target')
    if type(event['duration']) is not int or not 15<=event['duration']<=180:raise ValueError('Invalid reservation')

def validate_event(event,now):
    if not isinstance(event,dict) or set(event)!={'exercise','id','guest','action','target','duration','expires'}:raise ValueError('Unexpected hour-four event fields')
    identifiers(event['exercise'],event['id']);binding(event)
    if type(event['expires']) not in (int,float) or not math.isfinite(event['expires']) or not now<event['expires']<=now+15:raise ValueError('Expired hour-four authorization')
    return event

def validate(events,targets,allow_pilot=False):
    if not isinstance(events,list) or len(events)>256:raise ValueError('Invalid profile size')
    first=[];seen=set()
    for e in events:
        if not isinstance(e,dict):raise ValueError('Invalid event')
        if e.get('action') not in ACTIONS:
            first.append(e);continue
        if set(e)!={'id','guest','target','action','at','window','duration'}:raise ValueError('Unexpected manifest fields')
        identifiers(e['guest'],e['id']);binding(e)
        if e['guest'] not in targets or e['target'] not in targets[e['guest']]:raise ValueError('Unenrolled target')
        if type(e['window']) not in (int,float) or not math.isfinite(e['window']) or not 1<=e['window']<=15:raise ValueError('Invalid window')
        pilot=allow_pilot and len(events)==1 and e['id']==f"hour4-pilot-{e['guest']}-{e['target']}" and e['at']==3
        if type(e['at']) not in (int,float) or not math.isfinite(e['at']) or not (pilot or 10800<=e['at']) or e['at']+e['window']+e['duration']+30>14400:raise ValueError('Invalid hour-four offset')
    first3_validate(first,targets)
    for e in events:
        if e['id'] in seen:raise ValueError('Duplicate profile event')
        seen.add(e['id'])
    return events

def build_four_hours():
    from combined_schedule import build
    events=build()
    for n,((guest,target),action) in enumerate(FAULTS.items()):
        events.append(dict(id=f'all-hour4-{guest}-{target}',guest=guest,target=target,action=action,
                           at=10800+n*360,window=15,duration=180))
    return events

if __name__=='__main__':
    import pathlib,json
    pathlib.Path(__file__).with_name('first4h-all.json').write_text(json.dumps(build_four_hours(),indent=2)+'\n')
