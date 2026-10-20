"""Fixed all-guest first-three-hour schedule. No guest repair or fourth hour."""
import json,pathlib
GUESTS=('shop01','sql01','dc01','forum01','mail01','workstation01')
STOPS=(('shop01','apache'),('sql01','mariadb'),('dc01','dns'),
       ('forum01','web'),('mail01','smtp'),('shop01','apache'),
       ('sql01','mariadb'),('forum01','ftp'),('mail01','imap'),
       ('dc01','dns'),('mail01','web'),('shop01','apache'),
       ('sql01','mariadb'),('forum01','web'),('mail01','smtp'))
POLICIES=(('shop01','apache','business_disable'),
 ('sql01','mariadb','business_disable'),('dc01','dns','business_disable'),
 ('forum01','web','business_disable'),('mail01','smtp','business_disable'),
 ('shop01','apache','business_restart_off'),('sql01','mariadb','business_restart_off'),
 ('forum01','ftp','business_disable'),('mail01','imap','business_disable'),
 ('dc01','dns','business_restart_off'),('mail01','web','business_disable'),
 ('forum01','ftp','business_restart_off'),('mail01','smtp','business_restart_off'),
 ('mail01','imap','business_restart_off'),('shop01','apache','business_disable'))
def build():
    events=[]
    for n in range(12):
        for offset,guest in enumerate(GUESTS):
            events.append(dict(id=f'all-{guest}-popup-{n}',guest=guest,action='notice',
                               target='desktop',at=n*300+offset*30,window=15))
    for n,(guest,target) in enumerate(STOPS):
        events.append(dict(id=f'all-stop-{n}',guest=guest,target=target,
                           action='business_stop',at=3600+n*240,window=15,duration=180))
    for n,(guest,target,action) in enumerate(POLICIES):
        events.append(dict(id=f'all-policy-{n}',guest=guest,target=target,
                           action=action,at=7200+n*240,window=15,duration=180))
    return sorted(events,key=lambda e:e['at'])
if __name__=='__main__':
    pathlib.Path(__file__).with_name('first3h-all.json').write_text(json.dumps(build(),indent=2)+'\n')
