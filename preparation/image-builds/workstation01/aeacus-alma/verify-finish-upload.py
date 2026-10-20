"""Unprivileged verification of the uploaded script, with no guest configuration edits."""
import ast,base64,contextlib,hashlib,io,pathlib,re,shutil,subprocess,sys,tarfile,tempfile
from firewall.core.io.zone import Zone
from firewall.core.io.policy import policy_reader
from firewall.client import FirewallClientZoneSettings,FirewallClientPolicySettings
from firewall.command import FirewallCommand

source=pathlib.Path('/home/jwang/aeacus-setup/finish-workstation01.sh')
text=source.read_text()
subprocess.run(['bash','-n',str(source)],check=True)
blob=base64.b64decode(text.split("<<'SUMMIT_PAYLOAD'\n",1)[1].split('\nSUMMIT_PAYLOAD',1)[0])
pin=re.search(r"hexdigest\(\)=='([0-9a-f]{64})'",text).group(1)
assert hashlib.sha256(blob).hexdigest()==pin
with tempfile.TemporaryDirectory(prefix='summit-finish-validation-') as folder:
    root=pathlib.Path(folder)
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
        for item in archive.getmembers():
            name=pathlib.PurePosixPath(item.name)
            assert item.isfile() and not name.is_absolute() and '..' not in name.parts
            target=root/name; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(item).read())
            if item.name.endswith('.py'): ast.parse(target.read_bytes(),feature_version=(3,9))
    worker=ast.parse((root/'finish_workstation.py').read_text())
    zone=next(n.value.value for n in worker.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ZONE' for t in n.targets))
    Zone().check_name(zone)
    try: Zone().check_name('summit-workstation')
    except Exception: print('Installed firewalld rejects the original long name and accepts '+zone+'.')
    else: raise AssertionError('Long-name regression not reproduced')
    sys.path.insert(0,str(root/'probes'))
    from access import summary_field
    import trust
    anchors=trust.current_fingerprints()
    assert anchors and trust.TRAINING_CA_SHA256 in anchors,'Restored planted CA is not in current trust'
    assert not trust.check(11),'Restored fictional CA falsely passed'
    assert not (root/'training-ca').exists()
    print('Relocated trust probe reads the actual trust store and correctly detects the restored fictional CA without a reference file.')
    sample=Zone(); sample.name=zone; sample.target='default'; sample.services=['ssh','dhcpv6-client']; sample.interfaces=['ens160']
    rendered=io.StringIO()
    with contextlib.redirect_stdout(rendered):
        FirewallCommand().print_zone_info(zone,FirewallClientZoneSettings(sample.export_config()))
    assert summary_field(rendered.getvalue(),'target')=='default'
    builtin=policy_reader('allow-host-ipv6.xml','/usr/lib/firewalld/policies')
    settings=FirewallClientPolicySettings(builtin.export_config_dict())
    rendered=io.StringIO()
    with contextlib.redirect_stdout(rendered): FirewallCommand().print_policy_info('allow-host-ipv6',settings)
    assert summary_field(rendered.getvalue(),'target')=='CONTINUE'
    assert summary_field(rendered.getvalue(),'priority')=='-15000'
    expected={'rule family="ipv6" icmp-type name="'+kind+'" accept' for kind in ('neighbour-advertisement','neighbour-solicitation','router-advertisement','redirect','mld-listener-done','mld-listener-query','mld-listener-report','mld2-listener-report')}
    assert set(settings.getRichRules())==expected
    print('Actual installed zone/policy summary formatting and built-in IPv6 rules verified without D-Bus mutations.')
    print('Real-engine README/encryption compatibility is now a root preflight within the one sudo script; not claimed verified by this unprivileged validator.')
    subprocess.run(['/usr/bin/python3','-m','unittest','discover','-s',str(root/'probes'),'-p','test_*.py'],check=True)
    subprocess.run(['/usr/bin/python3','-m','unittest','discover','-s',str(root),'-p','test_*.py'],check=True)
print('Uploaded script hash, installed zone validation, bash/Python syntax and bundled tests passed; no configuration changed.')
print('Script SHA256: '+hashlib.sha256(source.read_bytes()).hexdigest())
