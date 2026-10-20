#Requires -RunAsAdministrator
param([ValidatePattern('^edge-verification(?:-r[0-9]+)?$')][string]$RecordName='edge-verification-r2')
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Import-Module ActiveDirectory
$root='C:\ProgramData\SummitCompetitionExpansion-20261004'
$record="$root\$RecordName"
$public='C:\SummitCompetition';$data='C:\SummitSupply';$payload='C:\ProgramData\SummitCompetition'
if($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong guest'}
if(Test-Path $record){throw 'Edge verification record already exists'}
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Build-Competition.ps1",[ref]$tokens,[ref]$errors);if($errors){throw 'Base syntax invalid'}
$defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false));foreach($name in @('Native','Private','Preserve','Probe','State','Score')){$f=@($defs | Where-Object Name -eq $name);$t=$f[0].Extent.Text;if($name -eq 'Probe'){$t=$t -replace '^function Probe','function BaseProbe'};Invoke-Expression $t}
$ast=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Expand-Competition.ps1",[ref]$tokens,[ref]$errors);if($errors){throw 'Expansion syntax invalid'};$defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false));foreach($name in @('Probe','SetControl','Preservation')){$f=@($defs | Where-Object Name -eq $name);Invoke-Expression $f[0].Extent.Text}
$extra=@('share-encryption','share-permission','share-ntfs','automation-acl','uac-consent','uac-desktop','defender','firewall','audit-logon','audit-process','updates','root-trust')
$base=@('casey','drew','privilege','contractor','smb','dns-update','dns-transfer','spooler','registry','logging','persistence','credentials','media','fq1','fq2','fq3');$checks=$base+$extra
$meta=Get-Content C:\aeacus\probes\targets.json -Raw | ConvertFrom-Json;$roster=$meta.Roster
$businessHash=(Get-FileHash "$data\Business\inventory.csv").Hash;$opsHash=(Get-FileHash "$data\Operations\inventory.csv").Hash;$maintenanceHash=(Get-FileHash "$data\Automation\inventory-maintenance.cmd").Hash
$domainUsers="$((Get-ADDomain).DomainSID)-513";$thumb=(Get-Content "$root\root-thumbprint.txt" -Raw).Trim()
$answers=Get-Content "$root\organizer-answers.json" -Raw | ConvertFrom-Json;$questions=@{};foreach($i in 1..3){$body=Get-Content "$public\Forensic Question $i.txt" -Raw;$questions["fq$i"]=([regex]::Split($body,'\r?\nAnswer:\s*\r?\n',2))[0]}
$testingForensics=$false
if(Get-ADUser -Filter "SamAccountName -eq 'svc.legacybackup.tmp'"){throw 'Temporary account-name conflict'}
Preservation
New-Item $record -ItemType Directory | Out-Null;Private $record
Copy-Item C:\aeacus\probes\Check-Competition.ps1,C:\aeacus\probes\Check-Extra.ps1 "$record"
Copy-Item "$root\manifest.json","$root\final-verification.json" $record
Stop-Service CSSClient
try{
 Copy-Item "$PSScriptRoot\Check-Competition.ps1","$PSScriptRoot\Check-Extra.ps1" C:\aeacus\probes -Force
 $results=New-Object 'System.Collections.Generic.List[object]'
 foreach($id in @('contractor','share-ntfs','automation-acl')){
  SetControl $id $true;if((Probe $id) -ne 'PASS'){throw "Protected mismatch: $id"};Preservation
  SetControl $id $false;if((Probe $id) -ne 'FAIL'){throw "Planted mismatch: $id"};Preservation
  SetControl $id $true;if((Probe $id) -ne 'PASS'){throw "Repaired mismatch: $id"};Preservation
  SetControl $id $false;if((Probe $id) -ne 'FAIL'){throw "Final mismatch: $id"};Preservation
  $results.Add([pscustomobject]@{Control=$id;Protected='PASS';Planted='FAIL';Repaired='PASS';Final='FAIL';Preservation='PASS';Time=(Get-Date).ToString('o')})
 }
 # Renaming an enabled synthetic account must not award disable/removal credit.
 try{
  Set-ADUser $meta.ContractorSID -SamAccountName svc.legacybackup.tmp
  if((Probe contractor) -ne 'FAIL'){throw 'Renamed enabled account incorrectly credited'}
  Set-ADUser $meta.ContractorSID -Enabled $false
  if((Probe contractor) -ne 'PASS'){throw 'Disabled renamed account not accepted'}
 }finally{Set-ADUser $meta.ContractorSID -SamAccountName svc.legacybackup -Enabled $true}
 if((Probe contractor) -ne 'FAIL'){throw 'Account identity restoration failed'}
 New-Item "$record\absent-account" -ItemType Directory | Out-Null
 Copy-Item C:\aeacus\probes\Check-Competition.ps1 "$record\absent-account"
 (Get-Content C:\aeacus\probes\targets.json -Raw).Replace($meta.ContractorSID,"$((Get-ADDomain).DomainSID)-2147483647") | Set-Content "$record\absent-account\targets.json"
 $absent=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$record\absent-account\Check-Competition.ps1" -Check contractor
 if($LASTEXITCODE -ne 0 -or ($absent -join "`n").Trim() -ne 'PASS'){throw 'Actual absent identity adapter failed'}
 # Check ACL ordering against Windows itself with an actual employee token.
 $ast=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Check-Extra.ps1",[ref]$tokens,[ref]$errors)
 $f=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'NoEmployeeWrite'},$true));Invoke-Expression $f[0].Extent.Text
 $fixture="$record\acl-fixture";New-Item $fixture -ItemType Directory | Out-Null
 Native {icacls.exe $fixture /grant ("*$domainUsers`:(OI)(CI)RX") | Out-Null}
 $file="$fixture\fixture.txt";'Synthetic ACL regression fixture only.' | Set-Content $file
 $acl=Get-Acl $fixture
 $deny=New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($domainUsers)),[Security.AccessControl.FileSystemRights]::Write,([Security.AccessControl.InheritanceFlags]::ObjectInherit -bor [Security.AccessControl.InheritanceFlags]::ContainerInherit),[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Deny)
 $acl.AddAccessRule($deny);Set-Acl $fixture $acl
 if(-not (NoEmployeeWrite $file)){throw 'Protected fixture ACL not recognized'}
 $acl=Get-Acl $file;$allow=New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($domainUsers)),[Security.AccessControl.FileSystemRights]::Modify,[Security.AccessControl.AccessControlType]::Allow);$acl.AddAccessRule($allow);Set-Acl $file $acl
 if(NoEmployeeWrite $file){throw 'Explicit grant hidden by inherited deny'}
 Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class SummitAclLogon {
 [DllImport("advapi32.dll", SetLastError=true, CharSet=CharSet.Unicode)] public static extern bool LogonUser(string user,string domain,string password,int type,int provider,out IntPtr token);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr token);
}
'@
 $credentials=Get-Content C:\ProgramData\SummitLab\Private\initial-domain-credentials.json -Raw | ConvertFrom-Json;$employee=@($credentials | Where-Object Sam -eq 'emma.wilson');$token=[IntPtr]::Zero
 if(-not [SummitAclLogon]::LogonUser('emma.wilson','CORP',$employee[0].Password,3,0,[ref]$token)){throw 'Employee token unavailable for native ACL test'}
 try{$context=[Security.Principal.WindowsIdentity]::Impersonate($token);try{[IO.File]::AppendAllText($file,'Native employee write succeeded.')}finally{$context.Undo();$context.Dispose()}}finally{[SummitAclLogon]::CloseHandle($token) | Out-Null}
 Remove-Item -LiteralPath $file;Remove-Item -LiteralPath $fixture
 [pscustomobject]@{RenamedEnabledAccount='FAIL';RenamedDisabledAccount='PASS';AbsentAccount='PASS';ExplicitAllowOverInheritedDeny='Writable';ActualEmployeeWrite='PASS';Time=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content "$record\regressions.json"
 foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Starting mismatch: $id"}}
 Copy-Item "$root\scoring.conf" C:\aeacus\scoring.conf;Private C:\aeacus\scoring.conf
 Score 0 edge-starting
 $testingForensics=$true
 foreach($id in $checks){SetControl $id $true};Preservation
 foreach($id in $checks){if((Probe $id) -ne 'PASS'){throw "Solution mismatch: $id"}}
 Score 100 solution
 foreach($id in $checks){SetControl $id $false};Preservation
 $testingForensics=$false
 foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Restoration mismatch: $id"}}
 Score 0 edge-restored
 $results | ConvertTo-Json -Depth 5 | Set-Content "$record\rehearsals.json"
 Remove-Item -LiteralPath C:\aeacus\scoring.conf
 Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html
 $manifest=Get-Content "$root\manifest.json" -Raw | ConvertFrom-Json
 $manifest.BaseProbeHash=(Get-FileHash C:\aeacus\probes\Check-Competition.ps1).Hash;$manifest.ExtraProbeHash=(Get-FileHash C:\aeacus\probes\Check-Extra.ps1).Hash;$manifest.Time=(Get-Date).ToString('o')
 $manifest | ConvertTo-Json -Depth 5 | Set-Content "$root\manifest.json"
 Start-Service CSSClient
 'Edge-case regressions and refreshed 0/100, 100/100, 0/100 validation passed.'
}catch{$_ | Out-String | Set-Content "$record\failure.txt";throw}
