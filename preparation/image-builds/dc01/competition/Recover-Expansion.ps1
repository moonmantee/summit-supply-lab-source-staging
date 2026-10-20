#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\SummitCompetitionExpansion-20261004'
if($env:COMPUTERNAME -ne 'DC01'){throw 'Wrong guest'}
$saved=Get-Content "$root\baseline.json" -Raw | ConvertFrom-Json
if($saved.Machine -ne 'DC01'){throw 'Recovery identity mismatch'}
foreach($r in (Get-Acl $root).Access){if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Untrusted recovery ACL'}}
Stop-Service CSSClient
Set-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System ConsentPromptBehaviorAdmin $saved.Consent
Set-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System PromptOnSecureDesktop $saved.SecureDesktop
Set-MpPreference -DisableRealtimeMonitoring $saved.RealtimeDisabled
Set-NetFirewallProfile -Profile Public -Enabled $saved.FirewallPublic
Set-Service wuauserv -StartupType $saved.UpdateStart
if($saved.UpdateStatus -eq 'Running'){Start-Service wuauserv}else{Stop-Service wuauserv -Force}
foreach($audit in $saved.Audit){
 if($audit.GUID -notin @('{0CCE9215-69AE-11D9-BED3-505054503030}','{0CCE922B-69AE-11D9-BED3-505054503030}')){throw 'Audit recovery scope mismatch'}
 $success=if($audit.Inclusion -match 'Success'){'enable'}else{'disable'};$failure=if($audit.Inclusion -match 'Failure'){'enable'}else{'disable'}
 & auditpol.exe /set ("/subcategory:"+$audit.GUID) "/success:$success" "/failure:$failure" | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Scoped audit restoration failed'}
}
$share=Get-SmbShare SummitOps -ErrorAction SilentlyContinue
if($share){if($share.Path -ne 'C:\SummitSupply\Operations'){throw 'Share recovery scope mismatch'};Remove-SmbShare SummitOps -Force}
$task=Get-ScheduledTask SummitInventoryMaintenance -ErrorAction SilentlyContinue
if($task){if($task.Actions.Arguments -ne '/d /c C:\SummitSupply\Automation\inventory-maintenance.cmd'){throw 'Task recovery scope mismatch'};Unregister-ScheduledTask SummitInventoryMaintenance -Confirm:$false}
if(Test-Path "$root\root-thumbprint.txt"){$thumb=(Get-Content "$root\root-thumbprint.txt" -Raw).Trim();$cert=Get-Item ("Cert:\LocalMachine\Root\"+$thumb) -ErrorAction SilentlyContinue;if($cert){if($cert.Subject -ne 'CN=Summit Legacy Training Root 20261004'){throw 'Certificate recovery scope mismatch'};Remove-Item -LiteralPath $cert.PSPath}}
if($thumb){$my=Get-Item ("Cert:\LocalMachine\My\"+$thumb) -ErrorAction SilentlyContinue;if($my){if($my.Subject -ne 'CN=Summit Legacy Training Root 20261004'){throw 'Certificate key recovery scope mismatch'};Remove-Item -LiteralPath $my.PSPath -DeleteKey}}
Import-Module ActiveDirectory;$sid="$((Get-ADDomain).DomainSID)-513"
foreach($path in @('C:\SummitSupply\Operations','C:\SummitSupply\Automation')){if(Test-Path $path){icacls.exe $path /grant:r ("*$sid`:(OI)(CI)RX") /T | Out-Null;if($LASTEXITCODE -ne 0){throw 'Owned directory ACL restoration failed'}}}
Copy-Item "$root\previous-scoring.dat" C:\aeacus\scoring.dat -Force
if(Test-Path C:\aeacus\scoring.conf){Remove-Item -LiteralPath C:\aeacus\scoring.conf}
if(Test-Path "$root\previous-readme.txt"){Copy-Item "$root\previous-readme.txt" C:\SummitCompetition\README.txt -Force}
if(Test-Path C:\aeacus\assets\ScoringReport.html){Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html}
Start-Service CSSClient
Set-Content "$root\recovery-applied.txt" 'Scoped extra controls restored; participant/business files retained; verify prior 16-check runtime and authentication before acceptance.'
