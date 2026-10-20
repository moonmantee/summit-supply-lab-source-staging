"""A fixed Wayland popup; desktop work always runs as UID1000, never root."""
import json,os,pathlib,stat,subprocess,time
PUBLIC=pathlib.Path('/var/lib/summit-caldera-notice')
def desktop_session():
    rows=subprocess.run(['/usr/bin/loginctl','list-sessions','--no-legend','--no-pager'],check=True,capture_output=True,text=True,timeout=3).stdout.splitlines()
    for line in rows:
        parts=line.split()
        if len(parts)<3 or not parts[0].isdigit() or parts[1:3]!=['1000','jwang']:continue
        result=subprocess.run(['/usr/bin/loginctl','show-session',parts[0],'-p','User','-p','Active','-p','Remote','-p','Type'],check=True,capture_output=True,text=True,timeout=3)
        values=dict(row.split('=',1) for row in result.stdout.splitlines() if '=' in row)
        if values!={'User':'1000','Active':'yes','Remote':'no','Type':'wayland'}:continue
        runtime=pathlib.Path('/run/user/1000')
        for path in (runtime/'wayland-0',):
            st=path.lstat()
            if stat.S_ISSOCK(st.st_mode) and st.st_uid==1000:return {'session':parts[0],'wayland':path.name}
    raise ValueError('No approved active Wayland console')
def popup(expires):
    if not time.time()<expires<=time.time()+15:raise ValueError('Expired notice')
    session=desktop_session()
    environment={'PATH':'/usr/bin:/bin','HOME':'/home/jwang','USER':'jwang','LOGNAME':'jwang',
      'XDG_RUNTIME_DIR':'/run/user/1000','WAYLAND_DISPLAY':session['wayland'],'GDK_BACKEND':'wayland',
      'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus','LANG':'en_US.UTF-8'}
    if not time.time()<expires:raise ValueError('Expired before launch')
    child=subprocess.Popen(['/usr/bin/python3','-I',str(PUBLIC/'show_notice.py'),str(float(expires))],
      user=1000,group=1000,extra_groups=[],env=environment,cwd='/',stdin=subprocess.DEVNULL,
      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    return {'outcome':'APPLIED','delivery':'LAUNCHED','session':session['session'],'uid':1000,'pid':child.pid}
