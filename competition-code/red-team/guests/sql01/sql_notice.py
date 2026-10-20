"""Fixed visible notices; no controller-supplied text or home-directory writes."""
import math
import os
import pathlib
import stat
import subprocess
import sys
import time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from fixture_contract import IDENTIFIER
def identifier(value):return isinstance(value,str) and IDENTIFIER.fullmatch(value)

NOTICE_DIR='/var/lib/summit-caldera-notices'
MESSAGE='RED TEAM WAS HERE'
POPUP_UNIT='summit-caldera-visible-notice.service'
POPUP_USERS={'1000':'jwang'}


def valid(exercise,event,expires,clock):
    if (not identifier(exercise) or not identifier(event)
            or type(expires) not in (int,float) or not math.isfinite(expires)
            or clock()>=expires):raise ValueError('invalid or expired notice')


def directory(root):
    root=pathlib.Path(root)
    if not root.is_absolute():raise ValueError('absolute notice directory required')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    fd=os.open('/',flags)
    try:
        for part in root.parts[1:]:
            following=os.open(part,flags,dir_fd=fd);os.close(fd);fd=following
            info=os.fstat(fd)
            owner=(info.st_uid==0 if os.geteuid()==0 else info.st_uid in (0,os.geteuid()))
            sticky=(os.geteuid()!=0 and info.st_uid==0 and info.st_mode & stat.S_ISVTX)
            if not owner or (info.st_mode & 0o022 and not sticky):raise ValueError('untrusted notice directory')
        result=fd;fd=None;return result
    finally:
        if fd is not None:os.close(fd)


def write_desktop(root,exercise,event,expires,clock=time.time):
    valid(exercise,event,expires,clock)
    root=pathlib.Path(root);name=exercise+'-'+event+'.txt'
    if os.name=='posix':
        parent=directory(root)
        try:
            if len(os.listdir(parent))>=1000:raise ValueError('notice storage limit reached')
            valid(exercise,event,expires,clock)
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=parent)
            os.fchmod(fd,0o644)
        finally:os.close(parent)
    else:
        if root.is_symlink() or not root.is_dir():raise ValueError('invalid notice directory')
        if len(list(root.iterdir()))>=1000:raise ValueError('notice storage limit reached')
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        f.write(MESSAGE+'\nExercise: '+exercise+'\nEvent: '+event+'\n')
        f.flush();os.fsync(f.fileno())
    return {'outcome':'APPLIED'}


def show_popup(exercise,event,expires,clock=time.time,runner=None):
    """Ask the fixed participant's user manager to display one dismissible dialog."""
    valid(exercise,event,expires,clock)
    runner=runner or subprocess.run
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    uid=getattr(os,'geteuid',lambda:1000)()
    if uid not in (0,1000,1003):raise ValueError('unapproved popup caller')
    if uid!=0:
        env.update({'XDG_RUNTIME_DIR':'/run/user/'+str(uid),
                    'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/'+str(uid)+'/bus'})
    def run(args,check=True):
        result=runner(args,check=check,capture_output=True,text=True,timeout=4,env=env)
        if len(result.stdout)>4096:raise ValueError('session response exceeds bound')
        return result
    sessions=run(['/usr/bin/loginctl','list-sessions','--no-legend','--no-pager']).stdout.splitlines()
    graphical=False;selected=None
    # Prefer the verified competitor account if both organizer and competitor are logged in.
    sessions=sorted(sessions[:32],key=lambda line:0 if line.split()[1:3]==['1003','summit_editor'] else 1)
    for line in sessions:
        valid(exercise,event,expires,clock)
        fields=line.split()
        if (len(fields)<3 or POPUP_USERS.get(fields[1])!=fields[2] or not identifier(fields[0])
                or (uid!=0 and fields[1]!=str(uid))):continue
        response=run(['/usr/bin/loginctl','show-session',fields[0],'--no-pager',
                      '-p','Name','-p','User','-p','Type','-p','Active','-p','Remote']).stdout
        details=dict(line.split('=',1) for line in response.splitlines() if '=' in line)
        if (details.get('Name')==fields[2] and details.get('User')==fields[1]
                and details.get('Type') in ('wayland','x11') and details.get('Active')=='yes'
                and details.get('Remote')=='no'):
            graphical=True;selected=fields[2];break
    if not graphical:return 'NO_GRAPHICAL_SESSION'
    # .host routes via the system bus, preserving ProtectHome=yes on the agent.
    # No display/user environment is read or executed with root privileges.
    options=['--user','--machine='+selected+'@.host'] if uid==0 else ['--user']
    if run(['/usr/bin/systemctl']+options+['is-active',POPUP_UNIT],check=False).returncode==0:
        return 'ALREADY_VISIBLE'
    valid(exercise,event,expires,clock)
    run(['/usr/bin/systemd-run']+options+['--quiet','--collect','--service-type=exec',
        '--unit='+POPUP_UNIT,'--property=TimeoutStopSec=1',
        '--property=NoNewPrivileges=yes','--property=MemoryMax=128M','--property=TasksMax=32',
        '/usr/bin/zenity','--info','--title=Red team notice','--text='+MESSAGE,
        '--no-markup','--width=420'])
    return 'STARTED'


def apply_notice(exercise,event,target,targets,expires,clock=time.time,runner=None):
    valid(exercise,event,expires,clock)
    if not identifier(target):raise ValueError('invalid notice target')
    if target=='desktop' and targets.get('desktop')==NOTICE_DIR:
        result=write_desktop(NOTICE_DIR,exercise,event,expires,clock)
        result['popup']=show_popup(exercise,event,expires,clock,runner)
        return result
    if target=='wall' and targets.get('wall')=='/usr/bin/wall':
        runner=runner or subprocess.run
        valid(exercise,event,expires,clock)
        runner(['/usr/bin/wall','--nobanner','--timeout','2'],
               input=MESSAGE+'\nEvent: '+event+'\n',text=True,check=True,timeout=4,
               capture_output=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        return {'outcome':'APPLIED'}
    raise ValueError('unapproved notice target')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Fixed visible-notice popup check')
    parser.add_argument('--popup-probe',action='store_true',required=True)
    parser.parse_args()
    result=show_popup('notice-probe','notice-probe',time.time()+15)
    print('Popup: '+result)
    if result!='STARTED':raise SystemExit('Active graphical session and no existing popup required')

