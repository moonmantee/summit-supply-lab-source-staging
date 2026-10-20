"""Organizer controls. Profiles are reviewed root-owned files; no automatic full run."""
import argparse
import json
import os
import pathlib
import pwd
import subprocess
import sys
import time

APP=pathlib.Path('/opt/summit-caldera-fixtures')
CONF=pathlib.Path('/etc/summit-caldera-fixtures/runtime/config.json')
def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('status','load','start','pause','stop'))
    parser.add_argument('profile',nargs='?',choices=('empty','marker','stop','containment','first3h','first3h-rehearsal','first3h-sql01','first3h-sql01-rehearsal','first3h-linux','first3h-linux-rehearsal','first3h-manual-check','first3h-dc01','dc01-popup','first3h-dc01-stop','first3h-dc01-disable','first3h-dc01-restart-off','dc01-expiry','first3h-forum01','forum01-popup','forum01-expiry','first3h-forum01-web-stop','first3h-forum01-ftp-stop','first3h-forum01-web-disable','first3h-forum01-ftp-disable','first3h-forum01-ftp-restart-off','mail01-popup','mail01-expiry','first3h-mail01','first3h-mail01-smtp-stop','first3h-mail01-smtp-disable','first3h-mail01-smtp-restart-off','first3h-mail01-imap-stop','first3h-mail01-imap-disable','first3h-mail01-imap-restart-off','first3h-mail01-web-stop','first3h-mail01-web-disable','first3h-workstation01','workstation01-popup','workstation01-expiry','first3h-all','first4h-all','hour4-shop01-apache-pilot','hour4-sql01-mariadb-pilot','hour4-dc01-dns-pilot','hour4-forum01-web-pilot','hour4-forum01-ftp-pilot','hour4-mail01-smtp-pilot','hour4-mail01-imap-pilot','hour4-mail01-web-pilot'))
    args=parser.parse_args()
    if os.geteuid()!=0:raise ValueError('Organizer root required')
    if args.command!='load':
        run('runuser','-u','summit-coordinator','--','/usr/bin/python3',str(APP/'fixture_coordinator.py'),
            '--config',str(CONF),args.command);return
    if not args.profile:raise ValueError('Choose a reviewed profile')
    if args.profile in ('first3h-rehearsal','first3h-sql01-rehearsal','first3h-linux-rehearsal'):
        raise ValueError('Historical timed-repair rehearsals are disabled under contestant-repair policy')
    config=json.loads(CONF.read_text());sys.path.insert(0,str(APP/'legacy'))
    from state import Store
    from scheduler import Engine
    from manifest import validate_scenario
    from fixture_coordinator import scoring
    store=Store(config['state']);engine=Engine(store,[])
    with store.transaction() as c:
        current=c.execute('SELECT * FROM exercises ORDER BY rowid DESC LIMIT 1').fetchone()
    if current['state']=='RUNNING':raise ValueError('Stop or pause the exercise before changing profile')
    profile=validate_scenario(json.loads((APP/'profiles'/(args.profile+'.json')).read_text()),
                             {g:v['targets'] for g,v in config['guests'].items()})
    if args.profile.startswith(('first3h','first4h')) and any(not config['guests'][e['guest']].get('business_enabled',False) for e in profile):
        raise ValueError('Each business guest must pass its baseline/preflight gate')
    if args.profile.startswith('first4h') and any(e['action'] in ('business_binary_rename','business_launch_fault') and not config['guests'][e['guest']].get('hour4_enabled',False) for e in profile):
        raise ValueError('Each hour-four guest must pass its native fault/manual-repair gate')
    run('systemctl','stop','summit-caldera-coordinator')
    if current['state'] in ('DISARMED','PAUSED'):engine.transition(current['id'],'stop')
    path=pathlib.Path(config['scenario']);temp=path.with_suffix('.next')
    owner=pwd.getpwnam('summit-coordinator')
    with open(temp,'xb') as output:output.write(json.dumps(profile).encode());output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),0o600)
    os.chown(temp,owner.pw_uid,owner.pw_gid);os.replace(temp,path)
    store.create_exercise(scoring(config['scoring_export'])['id'],duration_s=14400 if args.profile.startswith('first4h') else 10800 if args.profile.startswith('first3h') else 12600)
    run('systemctl','start','summit-caldera-coordinator');time.sleep(0.5)
    print('Loaded '+args.profile+' DISARMED; no event dispatched. Use explicit start for rehearsal.')

if __name__=='__main__':main()

