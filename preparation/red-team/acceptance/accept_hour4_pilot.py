"""One bounded hour-four fault; leave repairs to contestants, always clear dispatch."""
import argparse,json,os,pathlib,socket,sqlite3,subprocess,sys,time
APP=pathlib.Path('/opt/summit-caldera-fixtures')
PAIRS={('shop01','apache'):'shop01-https',('sql01','mariadb'):'shop01-https',
 ('dc01','dns'):'dc01-dns',('forum01','web'):'forum01-web',('forum01','ftp'):'forum01-ftp',
 ('mail01','smtp'):'mail01-smtp',('mail01','imap'):'mail01-imaps',('mail01','web'):'mail01-https'}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('guest');parser.add_argument('target');args=parser.parse_args()
 assert os.geteuid()==0
 service_id=PAIRS[args.guest,args.target]
 sys.path.insert(0,str(APP));sys.path.insert(0,'/home/jwang/summit-scoring')
 import scorer
 service=next(s for s in scorer.resolve_services(json.loads(pathlib.Path('/home/jwang/summit-scoring/config.json').read_text())) if s['id']==service_id)
 def command(*values):return subprocess.run(['/usr/bin/python3',str(APP/'fixture_control.py'),*values],check=True,capture_output=True,text=True).stdout
 def status():return json.loads(command('status'))
 def wait_ready():
  deadline=time.monotonic()+10
  while True:
   try:
    with socket.create_connection(('10.77.70.20',8772),timeout=1):return
   except OSError:
    if time.monotonic()>deadline:raise TimeoutError('Coordinator listener unavailable')
    time.sleep(.1)
 current=status();assert current['exercise']['state']=='DISARMED' and not current['events'] and current['profile_events']==0
 assert scorer.run_probe(service)[0]=='PASS','Business baseline is not healthy'
 profile='hour4-'+args.guest+'-'+args.target+'-pilot'
 events=json.loads((APP/'profiles'/(profile+'.json')).read_text());assert len(events)==1 and events[0]['duration']==15
 database='file:/home/jwang/summit-scoring/state/results.sqlite3?mode=ro'
 with sqlite3.connect(database,uri=True) as db:first=db.execute('SELECT COALESCE(max(id),0) FROM service_checks').fetchone()[0]
 destination=pathlib.Path('/var/backups/summit-caldera')/('hour4-pilot-'+args.guest+'-'+args.target+'-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
 receipt={'result':'IN_PROGRESS','guest':args.guest,'target':args.target,'service_id':service_id,'samples':[],'repair_attempted':False}
 def save():
  temp=destination.with_suffix('.next')
  with temp.open('x') as output:os.fchmod(output.fileno(),0o600);json.dump(receipt,output,indent=2);output.flush();os.fsync(output.fileno())
  os.replace(temp,destination)
 pilot_pass=False
 try:
  command('load',profile);wait_ready();command('start');start=time.monotonic()
  while time.monotonic()-start<150:
   current=status();probe=scorer.run_probe(service)[0]
   receipt['samples'].append({'time':time.time(),'elapsed':current['exercise']['elapsed'],'probe':probe,'events':current['events']})
   assert current['exercise']['state']=='RUNNING'
   assert not any(e['outcome'] in ('FAILED','REJECTED') for e in current['events']),'Guest rejected or failed fault'
   with sqlite3.connect(database,uri=True) as db:
    receipt['normal_scoring_checks']=[{'id':r[0],'status':r[1]} for r in db.execute('SELECT id,status FROM service_checks WHERE id>? AND service_id=? ORDER BY id',(first,service_id))]
   applied=len(current['events'])==1 and current['events'][0]['outcome']=='APPLIED'
   save()
   if applied and current['exercise']['elapsed']>=60 and probe=='DOWN' and any(c['status']=='DOWN' for c in receipt['normal_scoring_checks']):break
   time.sleep(3)
  else:raise TimeoutError('Native application/outage/scoring evidence incomplete within bound')
  pilot_pass=True
 except BaseException as error:
  receipt['result']='FAILED';receipt['error_type']=type(error).__name__;raise
 finally:
  try:
   if status()['exercise']['state'] in ('RUNNING','PAUSED','DISARMED'):command('stop')
   command('load','empty');wait_ready();receipt['safe_final']=status()
   assert receipt['safe_final']['exercise']['state']=='DISARMED' and not receipt['safe_final']['events'] and receipt['safe_final']['profile_events']==0
   if pilot_pass:receipt['result']='FAULT_AND_SCORING_PASS_MANUAL_REPAIR_PENDING'
  except BaseException as cleanup:
   receipt['result']='FAILED';receipt['cleanup_error_type']=type(cleanup).__name__;raise
  finally:save()
  print(receipt['result']+'; dispatch empty/DISARMED; manual repair required; private receipt '+str(destination),flush=True)

if __name__=='__main__':main()
