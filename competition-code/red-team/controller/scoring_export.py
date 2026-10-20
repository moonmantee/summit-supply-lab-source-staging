"""Fetch a fresh scoring receipt using a forced-command, read-only SSH identity."""
import subprocess,pathlib,json,time,os,tempfile
ROOT=pathlib.Path('/run/summit-caldera-scoring')
def export():
 command=['/usr/bin/ssh','-F','/dev/null','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=2','-o','UserKnownHostsFile=/etc/summit-caldera-fixtures/scoring-bridge/known_hosts','-i','/etc/summit-caldera-fixtures/scoring-bridge/id_ed25519','summit-score-reader@10.77.70.10']
 result=subprocess.run(command,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
 if len(result.stdout)>1024:raise ValueError('Oversize scoring receipt')
 value=json.loads(result.stdout)
 if set(value)!={'id','state','generated'} or not 0<=time.time()-value['generated']<=4:raise ValueError('Invalid or stale scoring receipt')
 if ROOT.is_symlink() or ROOT.stat().st_uid!=0 or ROOT.stat().st_mode&0o022:raise ValueError('Untrusted receipt directory')
 fd,name=tempfile.mkstemp(prefix='.state-',dir=ROOT)
 try:
  with os.fdopen(fd,'wb') as f:f.write(result.stdout);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
  os.replace(name,ROOT/'state.json')
 finally:
  if os.path.exists(name):os.unlink(name)
if __name__=='__main__':export()
