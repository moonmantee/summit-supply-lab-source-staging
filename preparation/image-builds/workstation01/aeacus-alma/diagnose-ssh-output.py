"""Observe installed sshd output with disposable config/key; never run a listener."""
import pathlib,subprocess,tempfile,sys,collections
sys.path.insert(0,str(pathlib.Path(__file__).parent/'probes'))
from access import ssh_allowed
with tempfile.TemporaryDirectory(prefix='summit-sshd-output-') as folder:
    root=pathlib.Path(folder)
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(root/'key')],check=True)
    config=root/'config'
    for policy,expected in (('AllowGroups jwang competitor-recovery linux-workstation-admins@corp.summit.test\n',True),('AllowGroups jwang competitor-recovery *\n',False),('AllowGroups jwang\n',False),('AllowGroups jwang competitor-recovery linux-workstation-admins@corp.summit.test\nDenyGroups competitor-recovery\n',False)):
        # Multiple host keys are a legitimate output shape on the real host.
        config.write_text('HostKey '+str(root/'key')+'\nHostKey '+str(root/'key')+'\n'+policy)
        p=subprocess.run(['/usr/sbin/sshd','-T','-f',str(config)],text=True,capture_output=True,check=True)
        repeated={k:v for k,v in collections.Counter(line.split()[0] for line in p.stdout.splitlines()).items() if v>1}
        actual=ssh_allowed(p.stdout,True)
        print('Full installed sshd output: expected=%s actual=%s repeated=%s'%(expected,actual,repeated))
        assert actual==expected,'Roster probe rejected/misclassified full OpenSSH output'
print('All four installed-OpenSSH roster integration cases passed; no listener/configuration changes.')
