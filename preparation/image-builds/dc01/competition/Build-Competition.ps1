#Requires -RunAsAdministrator
param([ValidateSet('Build','Recover')][string]$Mode='Build',[ValidatePattern('^20261004(?:-r[0-9]+)?$')][string]$RunTag='20261004-r3',[switch]$ResumePrepared)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Import-Module ActiveDirectory
$root="C:\ProgramData\SummitCompetitionBuild-$RunTag"
$public='C:\SummitCompetition';$data='C:\SummitSupply';$payload='C:\ProgramData\SummitCompetition'
$checks=@('casey','drew','privilege','contractor','smb','dns-update','dns-transfer','spooler','registry','logging','persistence','credentials','media','fq1','fq2','fq3')
function Native([scriptblock]$Command){& $Command;if($LASTEXITCODE -ne 0){throw "Native command failed: $LASTEXITCODE"}}
function Private([string]$Path){if((Get-Item -LiteralPath $Path).PSIsContainer){Native {icacls.exe $Path /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null}}else{Native {icacls.exe $Path /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' | Out-Null}}}
function Hash([string]$Value){$h=[Security.Cryptography.SHA256]::Create();try{([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value.Trim().ToLowerInvariant())))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function Preserve {
 foreach($name in @('NTDS','DNS','Netlogon','DFSR','W32Time','sshd')){if((Get-Service $name).Status -ne 'Running'){throw "Business service failed: $name"}}
 if((Resolve-DnsName dc01.corp.summit.test -Server 127.0.0.1 -Type A).IPAddress -notcontains '10.77.40.10'){throw 'Business DNS failed'}
 foreach($name in @('SYSVOL','NETLOGON')){if(-not (Get-SmbShare -Name $name)){throw 'Directory share failed'}}
 $credentials=Get-Content C:\ProgramData\SummitLab\Private\initial-domain-credentials.json -Raw | ConvertFrom-Json
 Add-Type -AssemblyName System.DirectoryServices.AccountManagement
 $context=New-Object System.DirectoryServices.AccountManagement.PrincipalContext([System.DirectoryServices.AccountManagement.ContextType]::Domain,'dc01.corp.summit.test')
 try { foreach($e in $roster | Where-Object Role -ne 'departed'){
  $u=Get-ADUser $e.SID -Properties LockedOut
  if($u.SamAccountName -ne $e.Account -or -not $u.Enabled -or $u.LockedOut){throw "Roster unavailable: $($e.Account)"}
  $secret=@($credentials | Where-Object Sam -eq $e.Account)
  if($secret.Count -ne 1){throw "Credential preservation test unavailable: $($e.Account)"}
  if(-not $context.ValidateCredentials($e.Account,$secret[0].Password,[System.DirectoryServices.AccountManagement.ContextOptions]::Negotiate)){throw "Fresh authentication failed: $($e.Account)"}
 }} finally {$context.Dispose()}
 foreach($e in $roster | Where-Object Role -eq 'admin'){
  if(@(Get-ADGroupMember "$((Get-ADDomain).DomainSID)-512" -Recursive | Where-Object {$_.SID.Value -eq $e.SID}).Count -ne 1){throw 'Required administrator removed'}
 }
 if(-not (Test-Path "$data\Business\inventory.csv")){throw 'Business content missing'}
 if((Get-FileHash "$data\Business\inventory.csv").Hash -ne $businessHash){throw 'Business content changed'}
}
function Probe([string]$Name){
 $answerRoot=if($testingForensics){"$root\answers"}else{$public}
 $out=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\aeacus\probes\Check-Competition.ps1 -Check $Name -AnswerRoot $answerRoot
 if($LASTEXITCODE -ne 0){throw "Probe ERROR: $Name"}
 $out=($out -join "`n").Trim();if($out -notin @('PASS','FAIL')){throw "Invalid probe output: $Name"};$out
}
function State([string]$Name,[bool]$Protected){
 switch($Name){
  'casey' {Set-ADUser $meta.Casey -Enabled (-not $Protected)}
  'drew' {Set-ADUser $meta.Drew -Enabled (-not $Protected)}
  'privilege' {if($Protected){if(@(Get-ADGroupMember 'Backup Operators' | Where-Object {$_.SID.Value -eq $meta.Maya}).Count){Remove-ADGroupMember 'Backup Operators' $meta.Maya -Confirm:$false}}else{Add-ADGroupMember 'Backup Operators' $meta.Maya}}
  'contractor' {Set-ADUser $meta.ContractorSID -Enabled (-not $Protected)}
  'smb' {Set-SmbServerConfiguration -RequireSecuritySignature $Protected -Confirm:$false}
  'dns-update' {if($Protected){Set-DnsServerPrimaryZone corp.summit.test -DynamicUpdate Secure}else{Set-DnsServerPrimaryZone corp.summit.test -DynamicUpdate NonsecureAndSecure}}
  'dns-transfer' {if($Protected){Set-DnsServerPrimaryZone corp.summit.test -SecureSecondaries NoTransfer}else{Set-DnsServerPrimaryZone corp.summit.test -SecureSecondaries TransferAnyServer}}
  {$_ -in @('spooler','registry')} {$name=if($Name -eq 'spooler'){'Spooler'}else{'RemoteRegistry'};if($Protected){Stop-Service $name -Force;Set-Service $name -StartupType Disabled}else{Set-Service $name -StartupType Automatic;Start-Service $name}}
  'logging' {$size=if($Protected){67108864}else{1048576};Native {wevtutil.exe sl Security "/ms:$size"}}
  'persistence' {
   if($Protected){Disable-ScheduledTask -TaskName SummitLegacyTelemetry | Out-Null;if(Test-Path "$payload\legacy-telemetry.cmd"){Remove-Item -LiteralPath "$payload\legacy-telemetry.cmd"}}
   else{Copy-Item "$root\evidence-payload.cmd" "$payload\legacy-telemetry.cmd";Enable-ScheduledTask SummitLegacyTelemetry | Out-Null}
  }
  'credentials' {if($Protected){if(Test-Path "$data\Contractor\password-notes.txt"){Remove-Item -LiteralPath "$data\Contractor\password-notes.txt"}}else{'SUMMIT-FICTIONAL-CREDENTIALS-20261004; demo only: summit_demo / NotARealPassword!7' | Set-Content "$data\Contractor\password-notes.txt"}}
  'media' {if($Protected){if(Test-Path "$data\Contractor\personal-media.txt"){Remove-Item -LiteralPath "$data\Contractor\personal-media.txt"}}else{'SUMMIT-UNAUTHORIZED-MEDIA-20261004; fictional personal video collection; no actual media included.' | Set-Content "$data\Contractor\personal-media.txt"}}
  {$_ -in @('fq1','fq2','fq3')} {$i=[int]$Name.Substring(2);$answer=if($Protected){$answers.($Name)}else{''};($questions.($Name)+"`r`nAnswer:`r`n"+$answer+"`r`n") | Set-Content "$root\answers\Forensic Question $i.txt" -Encoding UTF8}
 }
}
function Score([int]$Expected,[string]$Label){
 $report='C:\aeacus\assets\ScoringReport.html';if(Test-Path $report){Remove-Item -LiteralPath $report}
 # Only the solution rehearsal reads private disposable answers. Restore the
 # production configuration even if scoring fails; public answers stay blank.
 if($Label -eq 'solution'){
  $candidate=Get-Content "$root\scoring.conf"
  $candidate=$candidate | ForEach-Object {if($_ -match '-Check fq[123]'){$_ -replace "'\s*$",(" -AnswerRoot "+$root+"\answers'")}else{$_}}
  $candidate | Set-Content C:\aeacus\scoring.conf -Encoding ascii
 }
 Push-Location C:\aeacus
 try{Native {& .\aeacus.exe score *> "$root\score-$Label.log"}}finally{Pop-Location;if($Label -eq 'solution'){Copy-Item "$root\scoring.conf" C:\aeacus\scoring.conf -Force}}
 $html=Get-Content $report -Raw
 $match=[regex]::Match($html,'(\d+) out of (\d+) points received')
 if(-not $match.Success -or [int]$match.Groups[1].Value -ne $Expected -or $match.Groups[2].Value -ne '100'){throw "Score mismatch: $Label"}
 $results.Add([pscustomobject]@{Stage=$Label;Score=$Expected;Total=100;Time=(Get-Date).ToString('o')})
}
function Recovery {
 $saved=Get-Content "$root\baseline.json" -Raw | ConvertFrom-Json
 if($saved.Host -ne 'DC01' -or (Get-ADUser $saved.CaseySID).SamAccountName -ne 'casey.turner' -or (Get-ADUser $saved.DrewSID).SamAccountName -ne 'drew.parker' -or (Get-ADUser $saved.MayaSID).SamAccountName -ne 'maya.chen'){throw 'Recovery identity validation failed'}
 if(@($saved.Services).Count -ne 2 -or @($saved.Services | Where-Object Name -notin @('Spooler','RemoteRegistry')).Count){throw 'Recovery service scope mismatch'}
 foreach($rule in (Get-Acl $root).Access){if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Untrusted recovery directory ACL'}}
 if(Get-Service CSSClient -ErrorAction SilentlyContinue){Stop-Service CSSClient -ErrorAction Stop;Native {sc.exe delete CSSClient | Out-Null}}
 Set-ADUser $saved.CaseySID -Enabled $saved.CaseyEnabled
 Set-ADUser $saved.DrewSID -Enabled $saved.DrewEnabled
 $group=Get-ADGroupMember 'Backup Operators'
 if(@($group | Where-Object {$_.SID.Value -eq $saved.MayaSID}).Count -gt 0 -and -not $saved.MayaBackup){Remove-ADGroupMember 'Backup Operators' $saved.MayaSID -Confirm:$false}
 $synthetic=$null
 if($saved.ContractorSID){try{$synthetic=Get-ADUser -Identity $saved.ContractorSID -ErrorAction Stop}catch [Microsoft.ActiveDirectory.Management.ADIdentityNotFoundException]{}}
 if($synthetic){if(-not $saved.ContractorSID -or $synthetic.SID.Value -ne $saved.ContractorSID){throw 'Recovery identity mismatch'};Remove-ADUser $synthetic -Confirm:$false}
 Set-SmbServerConfiguration -RequireSecuritySignature $saved.Signing -Confirm:$false
 Set-DnsServerPrimaryZone corp.summit.test -DynamicUpdate $saved.DynamicUpdate -SecureSecondaries $saved.SecureSecondaries
 foreach($entry in $saved.Services){Set-Service $entry.Name -StartupType $entry.StartType;if($entry.Status -eq 'Running'){Start-Service $entry.Name}else{Stop-Service $entry.Name -Force}}
 Native {wevtutil.exe sl Security ("/ms:"+$saved.LogSize)}
 $task=Get-ScheduledTask -TaskName SummitLegacyTelemetry -ErrorAction SilentlyContinue
 if($task){Unregister-ScheduledTask SummitLegacyTelemetry -Confirm:$false}
 foreach($file in @("$payload\legacy-telemetry.cmd","$payload\telemetry-marker.txt","$data\Contractor\password-notes.txt","$data\Contractor\personal-media.txt")){if(Test-Path $file){Remove-Item -LiteralPath $file}}
 # The previous scoring tree is restored from its NTFS-preserving copy. Do not
 # erase participant/business files or any existing identity database.
 Native {robocopy.exe "$root\previous-aeacus" C:\aeacus /E /COPYALL /R:1 /W:1 | Out-Null; if($LASTEXITCODE -le 7){$global:LASTEXITCODE=0}}
 if(Test-Path "$root\runtime-recovery.json"){
  $runtime=Get-Content "$root\runtime-recovery.json" -Raw | ConvertFrom-Json
  if($runtime.Executable -ne 'C:\aeacus\phocus.exe'){throw 'Runtime recovery scope mismatch'}
  if($runtime.AddedExclusion -and -not $runtime.ExclusionPreviouslyPresent){Remove-MpPreference -ExclusionPath 'C:\aeacus\phocus.exe'}
 }
 Set-Content "$root\recovery-applied.txt" 'Scoped baseline restored; run business/authentication validation before claiming recovery accepted.'
}
if($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong guest/domain'}
if($Mode -eq 'Recover'){Recovery;exit}
if(-not $ResumePrepared){
if(Test-Path $root){throw 'Existing build/recovery record; inspect before any retry'}
foreach($path in @($public,$data,$payload)){if(Test-Path $path){throw "Scenario path conflict: $path"}}
if(Get-Service CSSClient -ErrorAction SilentlyContinue){throw 'Unexpected live scorer; preserve before cutover'}
if(Get-ScheduledTask -TaskName SummitLegacyTelemetry -ErrorAction SilentlyContinue){throw 'Task identity conflict'}
if(Get-ADUser -Filter "SamAccountName -eq 'svc.legacybackup'"){throw 'Account identity conflict'}
if((Get-FileHash "$PSScriptRoot\aeacus-win32-v2.1.1.zip").Hash -ne 'F5056D0808200C09FF7433CA082ABF4504836BDB1AC1CAD61F84B8F2894469D4'){throw 'Runtime archive integrity failure'}
if((Get-PSDrive C).Free -lt 2GB){throw 'Guest disk space insufficient'}
$roster=Get-Content "$PSScriptRoot\verified-roster.json" -Raw | ConvertFrom-Json
if($roster.Count -ne 20){throw 'Roster count mismatch'}
New-Item $root -ItemType Directory | Out-Null;Private $root
$casey=Get-ADUser casey.turner;$drew=Get-ADUser drew.parker;$maya=Get-ADUser maya.chen
$zone=Get-DnsServerZone corp.summit.test
$saved=[ordered]@{Host='DC01';Snapshot='Pre-Competition-DC01-20261004';CaseySID=$casey.SID.Value;CaseyEnabled=$casey.Enabled;DrewSID=$drew.SID.Value;DrewEnabled=$drew.Enabled;MayaSID=$maya.SID.Value;MayaBackup=(@(Get-ADGroupMember 'Backup Operators' | Where-Object {$_.SID.Value -eq $maya.SID.Value}).Count -gt 0);Signing=(Get-SmbServerConfiguration).RequireSecuritySignature;DynamicUpdate=$zone.DynamicUpdate.ToString();SecureSecondaries=$zone.SecureSecondaries.ToString();LogSize=(Get-WinEvent -ListLog Security).MaximumSizeInBytes;Services=@(Get-Service Spooler,RemoteRegistry | ForEach-Object {[pscustomobject]@{Name=$_.Name;Status=$_.Status.ToString();StartType=$_.StartType.ToString()}});ContractorSID=$null}
$saved | ConvertTo-Json -Depth 6 | Set-Content "$root\baseline.json"
Native {wevtutil.exe epl Security "$root\baseline-security.evtx"}
Native {robocopy.exe C:\aeacus "$root\previous-aeacus" /E /COPYALL /R:1 /W:1 | Out-Null;if($LASTEXITCODE -le 7){$global:LASTEXITCODE=0}}
Copy-Item $PSCommandPath "$root\Build-Competition.ps1"
Set-Content "$root\phase.txt" 'baseline-saved'
}else{
 if(-not (Test-Path "$root\baseline.json") -or (Get-Content "$root\phase.txt" -Raw).Trim() -ne 'failed-requires-scoped-recovery'){throw 'Unrecognized prepared checkpoint'}
 if((Get-Content "$root\failure.txt" -Raw) -notmatch "Access to the path 'C:\\aeacus\\scoring.conf' is denied|Probe ERROR: casey"){throw 'Resume only supports the diagnosed preparation failures'}
 Copy-Item "$root\failure.txt" ("$root\failure-before-resume-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.txt')
 foreach($rule in (Get-Acl $root).Access){if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Prepared checkpoint ACL mismatch'}}
 $saved=Get-Content "$root\baseline.json" -Raw | ConvertFrom-Json
 $roster=Get-Content "$PSScriptRoot\verified-roster.json" -Raw | ConvertFrom-Json
 $casey=Get-ADUser $saved.CaseySID;$drew=Get-ADUser $saved.DrewSID;$maya=Get-ADUser $saved.MayaSID;$contractor=Get-ADUser $saved.ContractorSID
 if($casey.Enabled -ne $saved.CaseyEnabled -or $drew.Enabled -ne $saved.DrewEnabled -or $contractor.SamAccountName -ne 'svc.legacybackup' -or $contractor.Enabled){throw 'Prepared account state mismatch'}
 if(@(Get-ADGroupMember 'Backup Operators' | Where-Object {$_.SID.Value -eq $saved.MayaSID}).Count -ne [int]$saved.MayaBackup){throw 'Prepared privilege state mismatch'}
 if((Get-SmbServerConfiguration).RequireSecuritySignature -ne $saved.Signing){throw 'Prepared SMB state mismatch'}
 $z=Get-DnsServerZone corp.summit.test;if($z.DynamicUpdate.ToString() -ne $saved.DynamicUpdate -or $z.SecureSecondaries.ToString() -ne $saved.SecureSecondaries){throw 'Prepared DNS state mismatch'}
 foreach($s in $saved.Services){$live=Get-Service $s.Name;if($live.Status.ToString() -ne $s.Status -or $live.StartType.ToString() -ne $s.StartType){throw 'Prepared service state mismatch'}}
 if((Get-WinEvent -ListLog Security).MaximumSizeInBytes -ne $saved.LogSize -or (Get-ScheduledTask SummitLegacyTelemetry).State -ne 'Disabled'){throw 'Prepared log/task state mismatch'}
 if(Get-Service CSSClient -ErrorAction SilentlyContinue){throw 'Unexpected scorer during prepared resume'}
 $businessHash=(Get-FileHash "$data\Business\inventory.csv").Hash
 $answers=Get-Content "$root\organizer-answers.json" -Raw | ConvertFrom-Json
 $payloadHash=(Get-FileHash "$root\evidence-payload.cmd").Hash.ToLowerInvariant()
 if($answers.fq3 -ne $payloadHash -or (Get-FileHash "$public\Evidence\legacy-telemetry.cmd.txt").Hash.ToLowerInvariant() -ne $payloadHash){throw 'Prepared forensic payload mismatch'}
 Preserve
 Copy-Item $PSCommandPath ("$root\Build-Resume-Prepared-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.ps1')
 Private C:\aeacus\scoring.conf
}
try {
 if(-not $ResumePrepared){
 foreach($path in @($public,"$public\Evidence",$data,"$data\Business","$data\Contractor",$payload,"$root\answers")){New-Item $path -ItemType Directory | Out-Null}
 Private $payload
 'SKU,Description,Quantity','SUM-100,Trail backpack,24','SUM-101,Water bottle,48' | Set-Content "$data\Business\inventory.csv"
 $businessHash=(Get-FileHash "$data\Business\inventory.csv").Hash
 Preserve
 $bytes=New-Object byte[] 32;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
 $pw=ConvertTo-SecureString ('Aa9!'+[Convert]::ToBase64String($bytes)) -AsPlainText -Force
 New-ADUser -Name 'Legacy Backup Contractor' -SamAccountName svc.legacybackup -Path 'CN=Users,DC=corp,DC=summit,DC=test' -AccountPassword $pw -Enabled $false -Description 'Synthetic competition-only identity; no business dependency'
 $contractor=Get-ADUser svc.legacybackup
 $saved.ContractorSID=$contractor.SID.Value;$saved | ConvertTo-Json -Depth 6 | Set-Content "$root\baseline.json"
 # Harmless, bounded payload: a marker only, with no network or secret access.
 '@echo off', 'echo Synthetic Summit telemetry marker. No network activity.>C:\ProgramData\SummitCompetition\telemetry-marker.txt', 'exit /b 0' | Set-Content "$root\evidence-payload.cmd" -Encoding ascii
 Copy-Item "$root\evidence-payload.cmd" "$public\Evidence\legacy-telemetry.cmd.txt"
 $payloadHash=(Get-FileHash "$root\evidence-payload.cmd").Hash.ToLowerInvariant()
 $action=New-ScheduledTaskAction -Execute 'C:\Windows\System32\cmd.exe' -Argument '/d /c C:\ProgramData\SummitCompetition\legacy-telemetry.cmd'
 $trigger=New-ScheduledTaskTrigger -Daily -At '03:17'
 $principal=New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount -RunLevel Limited
 $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 10)
 Register-ScheduledTask -TaskName SummitLegacyTelemetry -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
 Disable-ScheduledTask SummitLegacyTelemetry | Out-Null
 Native {icacls.exe $payload /grant '*S-1-5-19:(OI)(CI)M' | Out-Null}
 Export-ScheduledTask SummitLegacyTelemetry | Set-Content "$public\Evidence\scheduled-task.xml" -Encoding UTF8
 'Synthetic incident record - fictional training evidence', '2026-10-04T08:17:00-06:00 actor=CORP\svc.legacybackup action=REGISTER_TASK task=SummitLegacyTelemetry', 'payload=C:\ProgramData\SummitCompetition\legacy-telemetry.cmd' | Set-Content "$public\Evidence\incident.log"
 $answers=@{fq1='corp\svc.legacybackup';fq2='summitlegacytelemetry';fq3=$payloadHash}
 }
 $questions=@{
  fq1="Forensic Question 1`r`nQuestion: Which domain account registered the unauthorized task?`r`nEvidence: C:\SummitCompetition\Evidence\incident.log`r`nFormat: CORP\account (case insensitive)."
  fq2="Forensic Question 2`r`nQuestion: What is the unauthorized scheduled task's name?`r`nEvidence: C:\SummitCompetition\Evidence\incident.log and scheduled-task.xml`r`nFormat: task name only (case insensitive)."
  fq3="Forensic Question 3`r`nQuestion: What is the SHA-256 of the preserved inert payload?`r`nEvidence: C:\SummitCompetition\Evidence\legacy-telemetry.cmd.txt`r`nFormat: 64 hexadecimal characters; hash the preserved file bytes."
 }
 $answers | ConvertTo-Json | Set-Content "$root\organizer-answers.json"
 $portableRoster=@($roster | ForEach-Object {[pscustomobject]@{Account=$_.Account;Role=$_.Role;SID=$_.SID}})
 $meta=[pscustomobject]@{Casey=$casey.SID.Value;Drew=$drew.SID.Value;Maya=$maya.SID.Value;ContractorSID=$contractor.SID.Value;Roster=$portableRoster;AnswerHashes=@{fq1=(Hash $answers.fq1);fq2=(Hash $answers.fq2);fq3=(Hash $answers.fq3)}}
 if(-not $ResumePrepared){Expand-Archive "$PSScriptRoot\aeacus-win32-v2.1.1.zip" "$root\runtime"}
 Copy-Item "$root\runtime\aeacus-win32\*" C:\aeacus -Recurse -Force
 Copy-Item "$PSScriptRoot\Check-Competition.ps1" C:\aeacus\probes
 $meta | ConvertTo-Json -Depth 6 | Set-Content C:\aeacus\probes\targets.json
 Private C:\aeacus\probes
 $messages=@('Former sales employee access revoked','Former warehouse employee access revoked','Standard employee administrative privileges removed','Unauthorized contractor account disabled or removed','SMB signing required','DNS dynamic updates secured','DNS zone transfers disabled','Unneeded print service disabled','Unneeded remote registry service disabled','Security event retention capacity restored','Unauthorized persistence removed','Plaintext credential material removed','Unauthorized personal media removed','Forensic question 1 answered','Forensic question 2 answered','Forensic question 3 answered')
 $lines=@('name = "summit-dc01-competition"','title = "Summit Supply - DC01 Competition"','os = "Windows Server 2022"','user = "Administrator"','version = "2.1.1"','local = true','shell = false')
 $issues=@();$total=0
 for($i=0;$i -lt $checks.Count;$i++){
  $id=$checks[$i];$points=if($id -in @('persistence','fq1','fq2','fq3')){10}else{5};$total+=$points
  $category=switch($id){ {$_ -in @('casey','drew','privilege','contractor')}{'User Auditing'};{$_ -in @('smb','dns-update','dns-transfer')}{'Application Security'};{$_ -in @('spooler','registry')}{'Service Auditing'};'logging'{'Local Policy'};'persistence'{'Malware'};{$_ -in @('credentials','media')}{'Prohibited Files'};default{'Forensics Questions'}}
  $lines+=@('', '[[check]]',('message = "'+$messages[$i]+'"'),("points = $points"),'[[check.pass]]',"type = 'CommandOutput'",("cmd = '& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\aeacus\probes\Check-Competition.ps1 -Check "+$id+"'"),"value = 'PASS'")
  $planted=switch($id){'casey'{'Former sales account enabled'};'drew'{'Former warehouse account enabled'};'privilege'{'maya.chen is an effective Backup Operator'};'contractor'{'Synthetic svc.legacybackup account enabled'};'smb'{'SMB server signing not required'};'dns-update'{'Primary domain zone accepts insecure dynamic updates'};'dns-transfer'{'Primary domain zone permits arbitrary transfers'};'spooler'{'Print Spooler running and automatic'};'registry'{'Remote Registry running and automatic'};'logging'{'Security log limited to 1 MiB'};'persistence'{'Unauthorized LOCAL SERVICE marker task enabled with payload present'};'credentials'{'Fictional plaintext credential notes in business search scope'};'media'{'Fictional unauthorized personal media listing in business search scope'};default{'Public forensic answer blank'}}
  $issues+=[pscustomobject]@{ID=$id;Category=$category;Points=$points;Target=$id;PlantedState=$planted;Repair=$messages[$i];Policy='DC01 participant README required protection';Probe="Check-Competition.ps1 -Check $id";Outcomes=@('PASS','FAIL','ERROR');Dependencies=@('AD','DNS','roster');Preserve=@('employee authentication','directory shares','business inventory','organizer SSH');Recovery='Scoped baseline.json plus Pre-Competition-DC01-20261004 snapshot';Status='prepared';Evidence=@()}
 }
 if($total -ne 100 -or $checks.Count -ne 16){throw 'Scoring total mismatch'}
 $lines | Set-Content C:\aeacus\scoring.conf -Encoding ascii;Private C:\aeacus\scoring.conf
 Copy-Item C:\aeacus\scoring.conf "$root\scoring.conf"
 Copy-Item "$PSScriptRoot\README.txt" "$public\README.txt"
 # Normal users read evidence and README, and may save only the answer files.
 Native {icacls.exe $public /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null}
 $shell=New-Object -ComObject WScript.Shell
 foreach($id in $checks | Where-Object {$_ -like 'fq*'}){
  State $id $false;$i=[int]$id.Substring(2);Copy-Item "$root\answers\Forensic Question $i.txt" "$public\Forensic Question $i.txt"
  Native {icacls.exe "$public\Forensic Question $i.txt" /grant '*S-1-5-32-545:M' | Out-Null}
  $lnk=$shell.CreateShortcut("C:\Users\Public\Desktop\Forensic Question $i.lnk");$lnk.TargetPath='C:\Windows\System32\notepad.exe';$lnk.Arguments='"'+"$public\Forensic Question $i.txt"+'"';$lnk.Save()
 }
 foreach($item in @(@('DC01 Competition README',"$public\README.txt"),@('Summit Scoring Report','C:\aeacus\assets\ScoringReport.html'))){$lnk=$shell.CreateShortcut('C:\Users\Public\Desktop\'+$item[0]+'.lnk');$lnk.TargetPath=$item[1];$lnk.Save()}
 Push-Location C:\aeacus;try{Native {& .\aeacus.exe check *> "$root\check.log"}}finally{Pop-Location}
 $results=New-Object 'System.Collections.Generic.List[object]'
 $testingForensics=$true
 Set-Content "$root\phase.txt" 'rehearsing'
 foreach($id in $checks){
  State $id $true;if((Probe $id) -ne 'PASS'){throw "Protected state failed: $id"};Preserve
  State $id $false;if((Probe $id) -ne 'FAIL'){throw "Planted state failed: $id"};Preserve
  State $id $true;if((Probe $id) -ne 'PASS'){throw "Repaired state failed: $id"};Preserve
  State $id $false;if((Probe $id) -ne 'FAIL'){throw "Final planted state failed: $id"};Preserve
  $results.Add([pscustomobject]@{Control=$id;Protected='PASS';Planted='FAIL';Repaired='PASS';Final='FAIL';Preservation='PASS';Time=(Get-Date).ToString('o')})
  $results | ConvertTo-Json -Depth 6 | Set-Content "$root\rehearsals.json"
  "Rehearsed $id"
 }
 Score 0 starting
 foreach($id in $checks){State $id $true};Preserve
 foreach($id in $checks){if((Probe $id) -ne 'PASS'){throw "Combined solution failed: $id"}}
 Score 100 solution
 foreach($id in $checks){State $id $false};Preserve
 $testingForensics=$false
 foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Combined restoration failed: $id"}}
 Score 0 restored
 # Production service uses the fixed C:\aeacus path. Only real Phocus can prove
 # encrypted scoring; delete developer reports before the service starts.
 Push-Location C:\aeacus;try{Native {& .\aeacus.exe encrypt *> "$root\encrypt.log"}}finally{Pop-Location}
 if((Get-Item C:\aeacus\scoring.dat).Length -le 0){throw 'Encrypted runtime missing'}
 Private C:\aeacus\scoring.dat
 Remove-Item -LiteralPath C:\aeacus\scoring.conf
 Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html
 New-Service CSSClient -BinaryPathName 'C:\aeacus\phocus.exe' -DisplayName 'Summit DC01 Competition Scoring' -StartupType Automatic | Out-Null
 $start=Get-Date;Start-Service CSSClient
 $deadline=(Get-Date).AddMinutes(5);$verified=$false
 do{
  Start-Sleep -Seconds 3
  if((Get-Service CSSClient).Status -ne 'Running'){throw 'Production scoring service stopped'}
  $report=Get-Item C:\aeacus\assets\ScoringReport.html -ErrorAction SilentlyContinue
  if($report -and $report.LastWriteTime -ge $start){$html=Get-Content $report.FullName -Raw;if($html -match '0 out of 100 points received' -and $html -match '</html>'){$verified=$true;break}}
 }while((Get-Date) -lt $deadline)
 if(-not $verified){throw 'Fresh encrypted report deadline exceeded'}
 Preserve
 foreach($issue in $issues){$issue.Status='runtime-verified';$issue.Evidence=@('protected PASS','planted FAIL','repaired PASS','final planted FAIL','combined 0/100,100/100,0/100','fresh Phocus 0/100')}
 $manifest=[ordered]@{Machine='DC01';OS='Windows Server 2022 Standard build 20348';Domain='corp.summit.test';Address='10.77.40.10';Snapshot=$saved.Snapshot;Engine='Aeacus 2.1.1';Count=16;Points=100;StartingScore=0;SolutionScore=100;RestoredScore=0;Issues=$issues;ProbeSHA256=(Get-FileHash C:\aeacus\probes\Check-Competition.ps1).Hash;ConfigSHA256=(Get-FileHash "$root\scoring.conf").Hash;RuntimeSHA256=(Get-FileHash C:\aeacus\phocus.exe).Hash;Acceptance=@{Automated='PASS';Desktop='PENDING';Reboot='PENDING';SnapshotRestore='PENDING';Export='PENDING'};OrganizerBoundary='Build/recovery sources remain on guest during construction; remove/archive externally before participant export';Time=(Get-Date).ToString('o')}
 $manifest | ConvertTo-Json -Depth 8 | Set-Content "$root\manifest.json"
 $results | ConvertTo-Json -Depth 6 | Set-Content "$root\rehearsals.json"
 Set-Content "$root\phase.txt" 'runtime-verified'
 'Competition scoring deployed: 16 checks; 0/100 starting; full solution 100/100; fresh encrypted runtime 0/100. Manual acceptance pending.'
}catch{
 $_ | Out-String | Set-Content "$root\failure.txt"
 Set-Content "$root\phase.txt" 'failed-requires-scoped-recovery'
 throw
}
