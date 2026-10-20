"""Enable one fixed guest's hour-four load gate after all native pilots pass."""
import argparse,json,os,pathlib,pwd,socket,stat,subprocess,time
APP=pathlib.Path('/opt/summit-caldera-fixtures')
CONFIG=pathlib.Path('/etc/summit-caldera-fixtures/runtime/config.json')
EVIDENCE=pathlib.Path('/var/backups/summit-caldera')
TARGETS={'shop01':('apache',),'sql01':('mariadb',),'dc01':('dns',),
 'forum01':('web','ftp'),'mail01':('smtp','imap','web')}
SCORED={('shop01','apache'):'shop01-https',('sql01','mariadb'):'shop01-https',
 ('dc01','dns'):'dc01-dns',('forum01','web'):'forum01-web',('forum01','ftp'):'forum01-ftp',
 ('mail01','smtp'):'mail01-smtp',('mail01','imap'):'mail01-imaps',('mail01','web'):'mail01-https'}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('guest',choices=tuple(TARGETS));args=parser.parse_args()
 assert os.geteuid()==0 and socket.gethostname()=='score01'
 def status():return json.loads(subprocess.run(['/usr/bin/python3',str(APP/'fixture_control.py'),'status'],check=True,capture_output=True,text=True).stdout)
 def empty(value):return value['exercise']['state']=='DISARMED' and not value['events'] and value['profile_events']==0
 assert empty(status()),'Dispatch must be empty/DISARMED'
 receipts=[]
 for target in TARGETS[args.guest]:
  candidates=list(EVIDENCE.glob('hour4-pilot-'+args.guest+'-'+target+'-*.json'));assert candidates,'Missing native pilot'
  path=max(candidates,key=lambda p:p.stat().st_mtime);info=path.lstat()
  assert stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_uid==0 and not info.st_mode&0o077
  receipt=json.loads(path.read_text())
  assert receipt['guest']==args.guest and receipt['target']==target
  assert receipt['service_id']==SCORED[args.guest,target]
  assert receipt['result']=='NATIVE_FAULT_AND_MANUAL_REPAIR_PASS'
  assert receipt['manual_repair_verified'] is True and receipt['contact_reconnect_no_replay_verified'] is True
  assert receipt['manual_repair_normal_scoring']['status']=='PASS' and empty(receipt['safe_final'])
  down=[c['id'] for c in receipt['normal_scoring_checks'] if c['status']=='DOWN']
  repaired=receipt['manual_repair_normal_scoring']['id']
  assert down and all(type(value) is int for value in down) and type(repaired) is int and repaired>max(down),'Repair score must follow the fault score'
  receipts.append(str(path))
 owner=pwd.getpwnam('summit-coordinator');info=CONFIG.lstat()
 assert stat.S_ISREG(info.st_mode) and not CONFIG.is_symlink() and info.st_uid==owner.pw_uid and stat.S_IMODE(info.st_mode)==0o600
 before=CONFIG.read_bytes();config=json.loads(before);assert config['guests'][args.guest]['business_enabled'] is True
 assert config['guests'][args.guest].get('hour4_enabled') is False,'Gate already changed'
 config['guests'][args.guest]['hour4_enabled']=True;after=(json.dumps(config)+'\n').encode()
 backup=EVIDENCE/('hour4-gate-'+args.guest+'-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(mode=0o700)
 (backup/'config.json').write_bytes(before);(backup/'config.json').chmod(0o600)
 def publish(data):
  temp=CONFIG.with_suffix('.hour4-gate-next')
  with temp.open('xb') as output:os.fchmod(output.fileno(),0o600);os.fchown(output.fileno(),info.st_uid,info.st_gid);output.write(data);output.flush();os.fsync(output.fileno())
  os.replace(temp,CONFIG)
 def restart():
  subprocess.run(['systemctl','start','summit-caldera-coordinator'],check=True)
  deadline=time.monotonic()+10
  while True:
   try:
    with socket.create_connection(('10.77.70.20',8772),timeout=1):return
   except OSError:
    if time.monotonic()>deadline:raise TimeoutError('Coordinator unavailable')
    time.sleep(.1)
 subprocess.run(['systemctl','stop','summit-caldera-coordinator'],check=True)
 try:
  assert empty(status()) and CONFIG.read_bytes()==before,'Concurrent state/config change preserved'
  publish(after);restart();assert empty(status())
 except BaseException:
  subprocess.run(['systemctl','stop','summit-caldera-coordinator'],check=True)
  assert CONFIG.read_bytes() in (before,after),'Unknown config preserved; coordinator kept stopped'
  publish(before);restart();raise
 (backup/'receipt.json').write_text(json.dumps({'guest':args.guest,'result':'PASS','native_pilot_receipts':receipts,'dispatch_empty_disarmed':True,'full_schedule_started':False}));(backup/'receipt.json').chmod(0o600)
 print(args.guest+' hour-four load gate enabled; dispatch stays empty/DISARMED; '+str(backup))

if __name__=='__main__':main()
