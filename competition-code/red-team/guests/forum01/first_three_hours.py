"""Only the requested first180 minutes: notices, stops, startup/restart policy."""
import math
from fixture_contract import identifiers

DURATION=10800
BUSINESS_ACTIONS=frozenset(('business_stop','business_disable','business_restart_off'))
BUSINESS_TARGETS={'shop01':('apache','apache2.service'),'sql01':('mariadb','mariadb.service')}

def validate(events,targets):
    if not isinstance(events,list) or len(events)>256:raise ValueError('Invalid event count')
    seen=set()
    for event in events:
        if not isinstance(event,dict):raise ValueError('Invalid event')
        action=event.get('action');fields={'id','guest','action','target','at','window'}
        if action in BUSINESS_ACTIONS:fields.add('duration')
        if set(event)!=fields or action not in BUSINESS_ACTIONS|{'notice'}:raise ValueError('Unapproved first-three-hours action')
        identifiers(event['guest'],event['id']);identifiers(event['target'],'target')
        if event['id'] in seen or event['guest'] not in targets:raise ValueError('Unapproved guest or repeated event')
        seen.add(event['id'])
        for key,low,high in (('at',0,DURATION-1),('window',1,15)):
            value=event[key]
            if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid event timing')
        if action=='notice':
            if event['target'] not in ('desktop','wall'):raise ValueError('Unapproved notice')
        elif (event['target'] not in targets[event['guest']] or type(event['duration']) is not int
              or not 15<=event['duration']<=180 or event['at']+event['window']+event['duration']+30>DURATION):
            raise ValueError('Unapproved scored-service target or duration')
    return events

def build_schedule(guest,target):
    identifiers(guest,target)
    events=[{'id':'popup-'+str(minute),'guest':guest,'action':'notice','target':'desktop','at':minute*60,'window':15}
            for minute in range(0,60,5)]
    for minute in range(65,120,10):
        events.append({'id':'stop-'+str(minute),'guest':guest,'action':'business_stop','target':target,
                       'at':minute*60,'window':15,'duration':180})
    for i,minute in enumerate(range(125,180,10)):
        events.append({'id':'policy-'+str(minute),'guest':guest,
            'action':'business_disable' if i%2==0 else 'business_restart_off','target':target,
            'at':minute*60,'window':15,'duration':180})
    return validate(events,{guest:{target}})

def validate_event(event,now):
    fields={'exercise','id','guest','action','target','duration','expires'}
    if not isinstance(event,dict) or set(event)!=fields:raise ValueError('Invalid business event')
    identifiers(event['exercise'],event['id'])
    if (event['guest'] not in BUSINESS_TARGETS or event['target']!=BUSINESS_TARGETS[event['guest']][0] or event['action'] not in BUSINESS_ACTIONS
            or type(event['duration']) is not int or not 15<=event['duration']<=180
            or type(event['expires']) not in (int,float) or not math.isfinite(event['expires'])
            or not now<event['expires']<=now+15):raise ValueError('Unapproved or expired business event')
    return event

def build_linux_schedule():
    guests=list(BUSINESS_TARGETS);events=[]
    for guest in guests:
        for event in build_schedule(guest,BUSINESS_TARGETS[guest][0])[:12]:events.append({**event,'id':guest+'-'+event['id']})
    for phase,minutes in ((2,range(65,120,5)),(3,range(125,180,5))):
        for index,minute in enumerate(minutes):
            guest=guests[index%len(guests)]
            action='business_stop' if phase==2 else ('business_disable' if (index//len(guests))%2==0 else 'business_restart_off')
            events.append({'id':guest+'-'+str(minute),'guest':guest,'action':action,'target':BUSINESS_TARGETS[guest][0],'at':minute*60,'window':15,'duration':180})
    events.sort(key=lambda e:(e['at'],e['guest']))
    return validate(events,{guest:{BUSINESS_TARGETS[guest][0]} for guest in guests})
