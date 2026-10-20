"""Fixed Linux exercise profiles; each cycle requires fresh online authorization."""
import argparse
import json


def build_schedule(profile):
    events=[]
    def notice(at,target):
        events.append({'id':'notice-'+str(at),'at':at,'window':20 if profile=='rehearsal' else 60,
                       'guest':'workstation01','action':'notice','target':target})
    def outage(at,duration):
        events.append({'id':'demo-outage-'+str(at),'at':at,'window':10 if profile=='rehearsal' else 60,
                       'guest':'workstation01','action':'service_stop','target':'demo','duration':duration})
    def fault(at,action,duration,window=60):
        events.append({'id':'demo-'+action+'-'+str(at),'at':at,'window':window,
                       'guest':'workstation01','action':action,'target':'demo','duration':duration})
    if profile=='linux210-advanced':
        for i,at in enumerate(range(0,1800,300)):notice(at,'wall' if i%2==0 else 'desktop')
        for i,at in enumerate(range(2100,5400,600)):outage(at,(20,30,45,60,45,60)[i])
        fault(5700,'service_disable',60);fault(6300,'service_config',60)
        for at in (6900,6930,6960):fault(at,'service_stop',5,8)
        fault(7500,'service_disable',90);fault(8100,'service_config',90);notice(8700,'desktop')
        for at,action,duration in ((9300,'service_executable',90),(9900,'service_definition',90),
                                   (10500,'service_executable',120),(11100,'service_definition',120),
                                   (11700,'service_executable',120)):
            fault(at,action,duration)
        notice(12300,'wall')
    elif profile=='phased-rehearsal':
        notice(0,'desktop');notice(8,'wall')
        for at,action,duration in ((24,'service_stop',5),(50,'service_disable',8),(80,'service_config',8),
                                   (110,'service_stop',5),(140,'service_stop',5),(170,'service_stop',5),
                                   (200,'service_executable',8),(230,'service_definition',8)):
            fault(at,action,duration,8)
        notice(260,'desktop')
        for event in events:event['window']=8
    elif profile=='linux210':
        for i,at in enumerate(range(0,1800,300)):notice(at,'wall' if i%2==0 else 'desktop')
        for i,at in enumerate(range(2100,5400,600)):outage(at,(20,30,45,60,45,60)[i])
        for at in (5700,6900,8100):outage(at,90)
        notice(8700,'desktop')
        for at in (9300,10500,11700):outage(at,120)
        notice(12300,'wall')
    elif profile=='rehearsal':
        notice(0,'desktop');notice(8,'wall');outage(24,5)
        notice(38,'desktop');outage(54,5);notice(70,'wall')
    elif profile=='restart-rehearsal':
        # Recovery owns only an accepted outage, never future restart cycles.
        # Spacing allows five-second recovery plus timer/poll processing.
        for at in (0,15,30):
            events.append({'id':'demo-restart-'+str(at),'at':at,'window':8,
                           'guest':'workstation01','action':'service_stop',
                           'target':'demo','duration':5})
    else:raise ValueError('unknown schedule profile')
    return events


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',choices=('linux210','rehearsal','restart-rehearsal','linux210-advanced','phased-rehearsal'))
    args=parser.parse_args()
    print(json.dumps(build_schedule(args.profile),indent=2))
