$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -notin @('FORUM01','MAIL01')){throw 'Wrong machine'}
$rule=Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP'
if($rule.Enabled -ne 'True' -or $rule.Action -ne 'Allow' -or $rule.Direction -ne 'Inbound'){throw 'Unexpected SSH rule'}
$port=$rule|Get-NetFirewallPortFilter
if($port.LocalPort -ne '22'){throw 'Wrong port'}
$addresses=@(($rule|Get-NetFirewallAddressFilter).RemoteAddress)
if($addresses -contains 'Any'){throw 'Unexpected broad SSH source'}
if($addresses -contains '10.77.70.10'){Write-Output 'Scorer SSH already allowed'; exit 0}
$backup=Join-Path $env:ProgramData ('Summit-Network-Recovery-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backup|Out-Null
$acl=Get-Acl -LiteralPath $backup
$acl.SetAccessRuleProtection($true,$false)
foreach($sid in @('S-1-5-18','S-1-5-32-544')){
 $identity=[Security.Principal.SecurityIdentifier]::new($sid)
 $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
}
Set-Acl -LiteralPath $backup -AclObject $acl
@{Rule=$rule.Name;RemoteAddress=$addresses}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $backup 'ssh-rule.json')
Set-NetFirewallRule -Name $rule.Name -RemoteAddress ($addresses+'10.77.70.10')
if(@((Get-NetFirewallRule -Name $rule.Name|Get-NetFirewallAddressFilter).RemoteAddress) -notcontains '10.77.70.10'){throw 'Verification failed'}
Write-Output ('Allowed score01 SSH only; original rule saved at '+$backup)
