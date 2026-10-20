param([ValidateSet('Prepare','Build','Recover')][string]$Stage='Prepare')
#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'This build is pinned to MAIL01'}
if($Stage -ne 'Recover'){
 if((Get-FileHash C:\aeacus\aeacus.exe).Hash -ne '2CBD63BA2AA2284B6FEDE844EA389682B3FAD8229D530769AB537F686A15AB0F' -or (Get-FileHash C:\aeacus\phocus.exe).Hash -ne 'BF266B0E2BFCCB6AA871D61D2D9584ACBB2B11D19D5598E4435C78294A57DD4A'){throw 'Pinned scoring runtime integrity failed'}
}
Import-Module WebAdministration
. "$PSScriptRoot\Controls.ps1";. "$PSScriptRoot\Native.ps1";. "$PSScriptRoot\MailWeb.ps1";. "$PSScriptRoot\Probe.ps1"
$pointer='C:\ProgramData\SummitLab\MailCompetition-current.txt'
$public='C:\Users\Public\Documents\SummitMailCompetition';$scenario='C:\ProgramData\SummitMailScenario'
$reg='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System';$run='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run';$lsa='HKLM:\SYSTEM\CurrentControlSet\Control\Lsa';$update='HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU';$site='IIS:\Sites\MailEnable WebMail'
$ssh='C:\ProgramData\ssh\sshd_config';$sshd='C:\Windows\System32\OpenSSH\sshd.exe'
function Save-Json($Value,[string]$Path){$Value|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $Path -Encoding UTF8}
function Private-Dir([string]$Path){New-Item -ItemType Directory -Path $Path|Out-Null;& icacls.exe $Path /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F'|Out-Null;if($LASTEXITCODE){throw 'Private ACL failed'}}
function Phase([string]$Name){Save-Json ([ordered]@{phase=$Name;root=$root;utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json";Write-Output "PHASE $Name"}
function Password{$bytes=New-Object byte[] 24;$rng=[Security.Cryptography.RandomNumberGenerator]::Create();try{$rng.GetBytes($bytes);return 'Mm9!'+[Convert]::ToBase64String($bytes)}finally{$rng.Dispose()}}
function Reg-Set([string]$Path,[string]$Name,$Value,[string]$Kind='DWord'){if(-not(Test-Path $Path)){New-Item -Path $Path -Force|Out-Null};New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType $Kind -Force|Out-Null}
function Ssh-Set([string]$Name,[string]$Value){
 $lines=[IO.File]::ReadAllLines($ssh);$lines=@($lines|Where-Object {$_ -notmatch ('^\s*'+[regex]::Escape($Name)+'\s+')})
 [IO.File]::WriteAllLines($ssh,@("$Name $Value")+$lines,[Text.Encoding]::ASCII)
 & $sshd -t;if($LASTEXITCODE){throw 'Invalid SSH configuration'};Restart-Service sshd;Start-Sleep -Milliseconds 250
}
function Acl-Set([string]$Path,[bool]$Protected,[bool]$Confidential=$false){
 $sddl='O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)'
 if(-not$Confidential){$sddl+='(A;;FRFX;;;BU)'}
 if(-not$Protected){$sddl+=if($Confidential){'(A;;FR;;;BU)'}else{'(A;;FA;;;BU)'}}
 if((Get-Item -LiteralPath $Path).PSIsContainer){$acl=New-Object Security.AccessControl.DirectorySecurity;$sddl=$sddl.Replace('(A;;','(A;OICI;')}
 else{$acl=New-Object Security.AccessControl.FileSecurity}
 $acl.SetSecurityDescriptorSddlForm($sddl);Set-Acl -LiteralPath $Path -AclObject $acl
}
function Set-Control([string]$Id,[bool]$Protected){
 switch($Id){
  'U01'{if($Protected){Disable-LocalUser mail.contractor}else{Enable-LocalUser mail.contractor}}
  'U02'{$has=([ForumNative]::GroupSids('Administrators') -contains $meta.auditSid);if($Protected -and $has){Remove-LocalGroupMember Administrators -Member mail.audit}elseif(-not$Protected -and -not$has){Add-LocalGroupMember Administrators -Member mail.audit}}
  'S01'{Ssh-Set PermitEmptyPasswords $(if($Protected){'no'}else{'yes'})}
  'S02'{Ssh-Set DisableForwarding $(if($Protected){'yes'}else{'no'})}
  'S03'{Ssh-Set LoginGraceTime $(if($Protected){'60'}else{'600'})}
  'W01'{Set-WebConfigurationProperty -PSPath $site -Filter system.webServer/directoryBrowse -Name enabled -Value (-not$Protected)}
  'W02'{Set-WebConfigurationProperty -PSPath $site -Filter system.webServer/httpErrors -Name errorMode -Value $(if($Protected){'Custom'}else{'Detailed'})}
  'W03'{Clear-WebConfiguration -PSPath $site -Filter "system.webServer/security/requestFiltering/verbs/add[@verb='TRACE']";Add-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/verbs -Name '.' -Value @{verb='TRACE';allowed=(-not$Protected)}}
  'W04'{Set-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/requestLimits -Name maxAllowedContentLength -Value $(if($Protected){30000000}else{2147483647})}
  {$_ -in @('L01','L02','L03')}{
   $guid=@{L01='{0CCE922B-69AE-11D9-BED3-505054503030}';L02='{0CCE9235-69AE-11D9-BED3-505054503030}';L03='{0CCE9215-69AE-11D9-BED3-505054503030}'}[$Id]
   $enable=if($Protected){'enable'}else{'disable'}
   if($Id -eq 'L03'){& auditpol.exe /set /subcategory:$guid /failure:$enable|Out-Null}else{& auditpol.exe /set /subcategory:$guid /success:$enable|Out-Null};if($LASTEXITCODE){throw 'Audit setter failed'}
  }
  'P01'{Reg-Set $reg legalnoticecaption $(if($Protected){'Summit authorized use'}else{''}) String;Reg-Set $reg legalnoticetext $(if($Protected){'Authorized lab use only. Activity may be monitored.'}else{''}) String}
  'P02'{Reg-Set $reg InactivityTimeoutSecs $(if($Protected){900}else{0})}
  'P03'{Reg-Set $lsa RestrictAnonymousSAM ([int]$Protected)}
  'A01'{Acl-Set "$scenario\operations.ps1" $Protected}
  'A02'{Acl-Set "$scenario\Maintenance" $Protected}
  'A03'{Acl-Set "$scenario\confidential.txt" $Protected $true}
  'A04'{Acl-Set "$scenario\test_authorized_keys" $Protected}
  'M01'{
   $task=Get-ScheduledTask -TaskPath '\SummitMailScenario\' -TaskName MailboxCacheSync -ErrorAction SilentlyContinue
   if($Protected){if($task){Disable-ScheduledTask -InputObject $task|Out-Null}}
   elseif($task){Enable-ScheduledTask -InputObject $task|Out-Null}
   else{
    $action=New-ScheduledTaskAction -Execute 'C:\Windows\System32\cmd.exe' -Argument '/d /c "C:\ProgramData\SummitMailScenario\cache-marker.cmd"'
    $p=New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount -RunLevel Limited
    Register-ScheduledTask -TaskPath '\SummitMailScenario\' -TaskName MailboxCacheSync -Action $action -Principal $p -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 30)) -Description 'Inert lab marker only; no network or business data access'|Out-Null
   }
  }
  'M02'{if($Protected){if((Get-Item $run).GetValueNames() -contains 'SummitMailLegacy'){Remove-ItemProperty $run SummitMailLegacy}}else{Reg-Set $run SummitMailLegacy 'C:\Windows\System32\cmd.exe /d /c "C:\ProgramData\SummitMailScenario\startup-marker.cmd"' String}}
  'D01'{$r=Get-NetFirewallRule -Name SummitMail-UnnecessaryIngress -ErrorAction SilentlyContinue;if($Protected){if($r){Disable-NetFirewallRule -InputObject $r|Out-Null}}elseif($r){Enable-NetFirewallRule -InputObject $r|Out-Null}else{New-NetFirewallRule -Name SummitMail-UnnecessaryIngress -DisplayName 'Summit mail unused legacy ingress' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9999 -Profile Any|Out-Null}}
  'O01'{Reg-Set $update NoAutoUpdate ([int](-not$Protected))}
  'F01'{if($Protected){if(Test-Path "$public\Operations\fictional-credentials.txt"){Remove-Item -LiteralPath "$public\Operations\fictional-credentials.txt"}}else{Copy-Item "$root\fixtures\fictional-credentials.txt" "$public\Operations\fictional-credentials.txt"}}
  'F02'{if($Protected){if(Test-Path "$public\Operations\personal-media.zip"){Remove-Item -LiteralPath "$public\Operations\personal-media.zip"}}else{Copy-Item "$root\fixtures\personal-media.zip" "$public\Operations\personal-media.zip"}}
  default{throw 'Unknown control'}
 }
}
function Assert-Business{
 foreach($n in $original.services){if((Get-Service $n).Status -ne 'Running'){throw "Required service stopped: $n"}}
 foreach($f in $original.mailFiles){if((Get-FileHash -LiteralPath $f.Path).Hash -ne $f.Hash){throw 'Mail account/configuration data changed'}}
 if((Get-CimInstance Win32_ComputerSystem).Domain -ne 'corp.summit.test' -or -not(Test-ComputerSecureChannel)){throw 'Domain trust lost'}
 $current=[string]@(Get-WebBinding -Name 'MailEnable WebMail' -Protocol https)[0].certificateHash;if($current -ne $original.certificate){throw 'Webmail certificate changed'}
 $web=[MailWeb]::Read('https://webmail.corp.summit.test/Mondo/lang/sys/login.aspx',$original.certificate);if($web -notmatch '^200\n' -or $web -notmatch 'MailEnable|WebMail|username|password'){throw 'Pinned webmail preservation failed'}
 foreach($sid in $original.adminSids){if([ForumNative]::GroupSids('Administrators') -notcontains $sid){throw 'Existing administrative access changed'}}
 if($secrets){if(-not[ForumNative]::Authenticate('mail.fallback','MAIL01',$secrets.fallback,2)){throw 'Local fallback cannot authenticate'};if(-not[ForumNative]::Authenticate('mail.audit','MAIL01',$secrets.audit,2)){throw 'Standard account cannot authenticate'}}
 if(-not(Get-MpComputerStatus).RealTimeProtectionEnabled){throw 'Defender protection lost'}
 [pscustomobject]@{services='running';mailConfigHashes='unchanged';domainTrust=$true;webmailPinnedLeafStatus=200;nativeWindowsCertificateTrust='baseline failed';realMailTransactions='pending';existingAdminMembership='preserved'}
}
function Assert-Control([string]$Id,[string]$Expected,[string]$State){$actual=Invoke-MailCheck $Id;if($actual -ne $Expected){throw "$Id $State expected $Expected observed $actual"};[ordered]@{id=$Id;state=$State;verdict=$actual;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Compress|Add-Content "$root\matrix.jsonl";Write-Output "$Id $State $actual"}
function Test-AuditBehavior([string]$Id){
 $started=(Get-Date).AddSeconds(-1);$eventId=0;$target=$null
 switch($Id){
  'L01'{& cmd.exe /d /c exit 0;$eventId=4688;$target='cmd.exe'}
  'L02'{$name='mail.probe'+([guid]::NewGuid().ToString('N').Substring(0,6));try{New-LocalUser -Name $name -Password (ConvertTo-SecureString (Password) -AsPlainText -Force) -Disabled|Out-Null;$target=$name;$eventId=4720}finally{if(Get-LocalUser $name -ErrorAction SilentlyContinue){Remove-LocalUser $name}}}
  'L03'{if([ForumNative]::Authenticate('mail.audit','MAIL01',(Password),2)){throw 'Expected bounded failed logon unexpectedly succeeded'};$eventId=4625;$target='mail.audit'}
 }
 $deadline=(Get-Date).AddSeconds(12);$events=@()
 do{
  Start-Sleep -Milliseconds 500
  try{$events=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=$eventId;StartTime=$started} -ErrorAction Stop|Where-Object {$_.ToXml() -match [regex]::Escape($target)})}
  catch{if($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*'){throw}}
 }until($events.Count -gt 0 -or (Get-Date) -gt $deadline)
 if(-not$events.Count){throw "Required audit event $eventId not observed for $Id"}
 [ordered]@{id=$Id;eventId=$eventId;matchingEvents=$events.Count;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Compress|Add-Content "$root\audit-behavior.jsonl"
}
function Combined([string]$Name,[int]$Points){$r=@(foreach($id in Get-ControlIds){[pscustomobject]@{id=$id;verdict=Invoke-MailCheck $id}});if(@($r|Where-Object verdict -eq ERROR).Count){throw 'Combined probes contain errors'};$score=4*@($r|Where-Object verdict -eq PASS).Count;if($score -ne $Points){throw "$Name score $score expected $Points"};Save-Json ([ordered]@{name=$Name;score=$score;results=$r;preservation=Assert-Business}) "$root\$Name.json";Write-Output "$Name $score/100"}
function Restore-Original{
 if(Get-Service CSSClient -ErrorAction SilentlyContinue){Stop-Service CSSClient;& sc.exe delete CSSClient|Out-Null;if($LASTEXITCODE){throw 'Scorer removal failed'}}
 Copy-Item "$root\backup\sshd_config" $ssh -Force;Set-Acl -LiteralPath $ssh -AclObject (Get-Acl "$root\backup\sshd_config");& $sshd -t;if($LASTEXITCODE){throw 'Original SSH syntax failed'};Restart-Service sshd
 foreach($x in $original.registry){if($x.exists){Reg-Set $x.path $x.name $x.value $x.kind}elseif(Test-Path $x.path){if((Get-Item $x.path).GetValueNames() -contains $x.name){Remove-ItemProperty -Path $x.path -Name $x.name}}}
 & auditpol.exe /restore /file:"$root\backup\audit.csv"|Out-Null;if($LASTEXITCODE){throw 'Audit restoration failed'}
 Set-WebConfigurationProperty -PSPath $site -Filter system.webServer/directoryBrowse -Name enabled -Value $original.iis.directoryBrowse
 Set-WebConfigurationProperty -PSPath $site -Filter system.webServer/httpErrors -Name errorMode -Value $original.iis.errorMode
 Set-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/requestLimits -Name maxAllowedContentLength -Value $original.iis.maxRequest
 Clear-WebConfiguration -PSPath $site -Filter "system.webServer/security/requestFiltering/verbs/add[@verb='TRACE']"
 foreach($x in $original.iis.trace){Add-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/verbs -Name '.' -Value @{verb=$x.verb;allowed=$x.allowed}}
 $task=Get-ScheduledTask -TaskPath '\SummitMailScenario\' -TaskName MailboxCacheSync -ErrorAction SilentlyContinue;if($task){Stop-ScheduledTask -InputObject $task;Unregister-ScheduledTask -InputObject $task -Confirm:$false}
 if(Get-NetFirewallRule -Name SummitMail-UnnecessaryIngress -ErrorAction SilentlyContinue){Remove-NetFirewallRule -Name SummitMail-UnnecessaryIngress}
 if($meta){foreach($x in @(@{name='mail.contractor';sid=$meta.contractorSid},@{name='mail.audit';sid=$meta.auditSid},@{name='mail.fallback';sid=$meta.fallbackSid})){if(Get-LocalUser $x.name -ErrorAction SilentlyContinue){if((Get-LocalUser $x.name).SID.Value -ne $x.sid){throw 'Recovery identity mismatch'};Remove-LocalUser $x.name}}}
 foreach($p in @($public,$scenario,'C:\aeacus\probes')){if(Test-Path $p){$resolved=(Resolve-Path -LiteralPath $p).Path;if($resolved -ne $p){throw 'Recovery path mismatch'};Remove-Item -LiteralPath $p -Recurse -Force}}
 foreach($p in @('C:\aeacus\scoring.conf','C:\aeacus\scoring.dat','C:\aeacus\assets\ScoringReport.html','C:\aeacus\TeamID.txt')){if(Test-Path $p){Remove-Item -LiteralPath $p}}
 foreach($name in @('Summit Mail Competition README','Summit Mail Scoring Report')){$p="C:\Users\Public\Desktop\$name.lnk";if(Test-Path $p){Remove-Item -LiteralPath $p}}
 $secrets=$null;Assert-Business|Out-Null;Phase rollback-verified
}
if($Stage -eq 'Prepare'){
 if(Test-Path $pointer){
  $prior=(Get-Content $pointer -Raw).Trim()
  if($prior -notmatch '^C:\\ProgramData\\SummitLab\\MailCompetition-[a-f0-9]{32}$' -or (Get-Content "$prior\status.json" -Raw|ConvertFrom-Json).phase -ne 'rollback-verified'){throw 'Prior build is not a verified rollback; diagnose/recover before a new run'}
  $saved=Get-Content "$prior\backup\original.json" -Raw|ConvertFrom-Json
  if((Get-FileHash $ssh).Hash -ne (Get-FileHash "$prior\backup\sshd_config").Hash -or (Get-Acl $ssh).Sddl -ne $saved.sshSddl){throw 'Prior SSH recovery mismatch'}
  foreach($x in $saved.registry){$key=Get-Item $x.path -ErrorAction SilentlyContinue;$exists=($key -and $key.GetValueNames() -contains $x.name);if([bool]$exists -ne $x.exists -or ($exists -and $key.GetValue($x.name) -ne $x.value)){throw 'Prior registry recovery mismatch'}}
  if([bool](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/directoryBrowse -Name enabled)) -ne $saved.iis.directoryBrowse -or [string](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/httpErrors -Name errorMode)) -ne $saved.iis.errorMode -or [long](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/requestLimits -Name maxAllowedContentLength)) -ne $saved.iis.maxRequest){throw 'Prior IIS recovery mismatch'}
  $auditCurrent="$prior\backup\verify-audit-$([guid]::NewGuid().ToString('N')).csv"
  & auditpol.exe /backup /file:$auditCurrent|Out-Null;if($LASTEXITCODE){throw 'Recovery audit validation failed'}
  # auditpol /restore materializes empty global-SACL rows absent from the original backup.
  # Exact empty rows are equivalent to absence; any actual policy or SACL content must match.
  $old=@(Get-Content "$prior\backup\audit.csv"|Where-Object {$_ -notmatch '^MAIL01,,(?:FileGlobalSacl|RegistryGlobalSacl),,,,$'})
  $now=@(Get-Content $auditCurrent|Where-Object {$_ -notmatch '^MAIL01,,(?:FileGlobalSacl|RegistryGlobalSacl),,,,$'})
  if(@(Compare-Object $old $now).Count){throw 'Prior audit recovery mismatch'}
  Write-Output 'Verified exact known prior recovery; preserving its evidence and allocating a new record'
  Remove-Item -LiteralPath $pointer
 }
 foreach($p in @($public,$scenario,'C:\aeacus\probes','C:\aeacus\scoring.conf','C:\aeacus\scoring.dat','C:\aeacus\TeamID.txt','C:\aeacus\assets\ScoringReport.html','C:\Users\Public\Desktop\Summit Mail Competition README.lnk','C:\Users\Public\Desktop\Summit Mail Scoring Report.lnk')){if(Test-Path $p){throw "Unexpected existing resource $p"}}
 if(Get-ScheduledTask -TaskPath '\SummitMailScenario\' -TaskName MailboxCacheSync -ErrorAction SilentlyContinue){throw 'Existing scenario task conflict'}
 if((Get-Item $run).GetValueNames() -contains 'SummitMailLegacy'){throw 'Existing scenario startup conflict'}
 foreach($n in @('mail.fallback','mail.audit','mail.contractor')){if([ForumNative]::UserFlags($n) -ne -1){throw "Synthetic identity conflict $n"}}
 if(Get-Service CSSClient -ErrorAction SilentlyContinue){throw 'Existing scoring service'}
 if((Get-Service wuauserv).StartType -eq 'Disabled'){throw 'Baseline update service disabled; requires separate recovery design'}
 if(Get-NetFirewallRule -Name SummitMail-UnnecessaryIngress -ErrorAction SilentlyContinue){throw 'Existing firewall rule conflict'}
 $root='C:\ProgramData\SummitLab\MailCompetition-'+[guid]::NewGuid().ToString('N');Private-Dir $root;Private-Dir "$root\backup";Private-Dir "$root\fixtures"
 $root|Set-Content $pointer;Phase backing-up
 $values=@(@{p=$reg;n='legalnoticecaption'},@{p=$reg;n='legalnoticetext'},@{p=$reg;n='InactivityTimeoutSecs'},@{p=$lsa;n='RestrictAnonymousSAM'},@{p=$run;n='SummitMailLegacy'},@{p=$update;n='NoAutoUpdate'})
 $saved=@(foreach($v in $values){$key=Get-Item $v.p -ErrorAction SilentlyContinue;$exists=($key -and $key.GetValueNames() -contains $v.n);[ordered]@{path=$v.p;name=$v.n;exists=[bool]$exists;kind=$(if($exists){[string]$key.GetValueKind($v.n)}else{'DWord'});value=$(if($exists){$key.GetValue($v.n)}else{$null})}})
 $original=[ordered]@{registry=$saved;adminSids=[ForumNative]::GroupSids('Administrators');services=@(Get-Service|Where-Object {$_.Name -like 'ME*' -or $_.Name -in @('sshd','W3SVC','WinDefend')}|ForEach-Object {$_.Name});mailFiles=@(Get-ChildItem 'C:\Program Files (x86)\Mail Enable\Config' -File -Filter *.TAB|Get-FileHash|Select-Object Path,Hash);certificate=[string]@(Get-WebBinding -Name 'MailEnable WebMail' -Protocol https)[0].certificateHash;sshSddl=(Get-Acl $ssh).Sddl;iis=@{directoryBrowse=[bool](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/directoryBrowse -Name enabled));errorMode=[string](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/httpErrors -Name errorMode));maxRequest=[long](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/requestLimits -Name maxAllowedContentLength));trace=@(Get-WebConfiguration -PSPath $site -Filter "system.webServer/security/requestFiltering/verbs/add[@verb='TRACE']"|Select-Object verb,allowed)}}
 Save-Json $original "$root\backup\original.json"
 Copy-Item $ssh "$root\backup\sshd_config";Set-Acl "$root\backup\sshd_config" (Get-Acl $ssh)
 Copy-Item C:\Windows\System32\inetsrv\config\applicationHost.config "$root\backup\applicationHost.config"
 & auditpol.exe /backup /file:"$root\backup\audit.csv"|Out-Null;if($LASTEXITCODE){throw 'Audit backup failed'}
 Copy-Item "$PSScriptRoot\*.ps1" $root
 $secrets=$null;Assert-Business|Out-Null
 Compress-Archive -Path "$root\backup\*" -DestinationPath "$root\prebuild-recovery.zip"
 Phase backup-ready;Get-FileHash "$root\prebuild-recovery.zip"|Select-Object Path,Hash|ConvertTo-Json;exit
}
if(-not(Test-Path $pointer)){throw 'Recovery pointer missing'};$root=(Get-Content $pointer -Raw).Trim()
if($root -notmatch '^C:\\ProgramData\\SummitLab\\MailCompetition-[a-f0-9]{32}$'){throw 'Recovery root invalid'}
$original=Get-Content "$root\backup\original.json" -Raw|ConvertFrom-Json
if(Test-Path "$root\metadata.json"){$meta=Get-Content "$root\metadata.json" -Raw|ConvertFrom-Json}
if(Test-Path "$root\secrets.json"){$secrets=Get-Content "$root\secrets.json" -Raw|ConvertFrom-Json}
if($Stage -eq 'Recover'){Restore-Original;exit}
if((Get-Content "$root\status.json" -Raw|ConvertFrom-Json).phase -ne 'backup-ready'){throw 'Unknown interrupted phase; scoped diagnosis/recovery required'}
try{
 Phase preparing-scenario
 $secrets=[ordered]@{fallback=Password;audit=Password;contractor=Password};Save-Json $secrets "$root\secrets.json"
 $meta=[ordered]@{machine='MAIL01';snapshot='MAIL01-before-competition-20261004';issueCount=25;points=100;expectedStart=0;expectedSolution=100;fallbackSid='';auditSid='';contractorSid='';credentialHash='';archiveHash='';issueManifest=@($Controls|ForEach-Object {$_+@{points=4;status='planned';probe="Probe.ps1 -Check $($_.id)";recovery='Scoped original state or exact build-owned resource';preservation='MailEnable business services/data, domain trust, organizer/fallback'}})}
 foreach($x in @(@{n='mail.fallback';p='fallback';sid='fallbackSid'},@{n='mail.audit';p='audit';sid='auditSid'},@{n='mail.contractor';p='contractor';sid='contractorSid'})){
  New-LocalUser -Name $x.n -Password (ConvertTo-SecureString $secrets[$x.p] -AsPlainText -Force) -Disabled -Description 'Synthetic Summit mail competition identity'|Out-Null
  $meta[$x.sid]=(Get-LocalUser $x.n).SID.Value;Save-Json $meta "$root\metadata.json"
  Add-LocalGroupMember Users -Member $x.n
 }
 Add-LocalGroupMember Administrators -Member mail.fallback;Enable-LocalUser mail.fallback;Enable-LocalUser mail.audit
 foreach($p in @($public,"$public\Operations",$scenario,"$scenario\Maintenance")){New-Item -ItemType Directory -Path $p|Out-Null}
 Acl-Set $scenario $true
 foreach($x in @(@{name='operations.ps1';text="Write-Output 'Summit authorized synthetic maintenance fixture'"},@{name='confidential.txt';text='Fictional confidential shipping plan. Preserve this business fixture.'},@{name='test_authorized_keys';text='INERT TEST FIXTURE - NOT A USABLE SSH KEY'})){[IO.File]::WriteAllText("$scenario\$($x.name)",$x.text,[Text.Encoding]::ASCII)}
 foreach($name in @('cache-marker','startup-marker')){[IO.File]::WriteAllText("$scenario\$name.cmd","@echo off`r`nrem INERT SIMULATION ONLY - NO NETWORK OR BUSINESS FILE ACCESS`r`nexit /b 0`r`n",[Text.Encoding]::ASCII)}
 'Summit Mail operations business document. Preserve this file.'|Set-Content "$public\Operations\operations-business.txt"
 "FICTIONAL-TRAINING-CREDENTIALS`r`nexercise_token=NOT-REAL-$([guid]::NewGuid())"|Set-Content "$root\fixtures\fictional-credentials.txt" -Encoding ASCII
 'Synthetic unauthorized personal media listing.'|Set-Content "$root\fixtures\media-list.txt"
 Compress-Archive -LiteralPath "$root\fixtures\media-list.txt" -DestinationPath "$root\fixtures\personal-media.zip"
 $meta.credentialHash=(Get-FileHash "$root\fixtures\fictional-credentials.txt").Hash;$meta.archiveHash=(Get-FileHash "$root\fixtures\personal-media.zip").Hash
 Save-Json $meta "$root\metadata.json"
 Private-Dir C:\aeacus\probes;Copy-Item "$PSScriptRoot\Probe.ps1","$PSScriptRoot\Native.ps1" C:\aeacus\probes;Save-Json $meta C:\aeacus\probes\metadata.json
 . C:\aeacus\probes\Probe.ps1
 $policies=($Controls|ForEach-Object {'<li>'+[Net.WebUtility]::HtmlEncode($_.policy)+'</li>'}) -join "`n"
 $readme="<!doctype html><html><head><meta charset='utf-8'><title>Summit MAIL01 Competition</title><style>body{max-width:900px;margin:40px auto;font:18px/1.6 Arial;padding:20px}h1,h2{color:#174166}</style></head><body><h1>Summit Supply MAIL01</h1><p>Windows Server 2022 / MailEnable 10.59 / corp.summit.test. 25 security objectives, 100 points. Preserve existing mailboxes, mail delivery, authorized authentication, webmail, domain trust and existing organizer access.</p><p>Authorized added local identities: mail.fallback (administrator) and mail.audit (standard). Existing labadmin remains authorized. Do not remove IME_ADMIN or IME_USER service identities. Organizer provides generated event passwords privately.</p><p>Maintain deployed SMTP 25/587, IMAP 143, POP 110, HTTPS webmail 443, required Windows domain services and organizer SSH 22. Port 993 was absent before this build; do not claim it is an established service. Preserve firewall profiles and existing certificates. Windows native certificate trust was failing before the build.</p><h2>Security policy</h2><ul>$policies</ul><p>Scenario fixture directory: C:\ProgramData\SummitMailScenario. Prohibited-content search scope: $public\Operations. Inert payloads are harmless training artifacts. Do not delete business fixtures to satisfy permission checks. No forensic objectives in this round.</p><h2>Scoring and recovery</h2><p>Use the Public Desktop report link, or open C:\aeacus\assets\ScoringReport.html. Refresh to read current results. Do not tamper with the scorer. Contact the organizer for console recovery; do not revert snapshots during competition.</p></body></html>"
 [IO.File]::WriteAllText("$public\README.html",$readme,[Text.Encoding]::UTF8)
 $shell=New-Object -ComObject WScript.Shell
 foreach($x in @(@{n='Summit Mail Competition README';p="$public\README.html"},@{n='Summit Mail Scoring Report';p='C:\aeacus\assets\ScoringReport.html'})){$lnk=$shell.CreateShortcut("C:\Users\Public\Desktop\$($x.n).lnk");$lnk.TargetPath=$x.p;$lnk.Save()}
 Phase rehearsing
 foreach($id in Get-ControlIds){
  Set-Control $id $true;Assert-Control $id PASS protected
  if($id -in @('L01','L02','L03')){Test-AuditBehavior $id}
  Set-Control $id $false;Assert-Control $id FAIL planted
  if($id -eq 'U01' -and -not[ForumNative]::Authenticate('mail.contractor','MAIL01',$secrets.contractor,2)){throw 'Unauthorized planted account cannot authenticate'}
  if($id -like 'A*'){
   Set-Control U02 $true;$path=@{A01="$scenario\operations.ps1";A02="$scenario\Maintenance";A03="$scenario\confidential.txt";A04="$scenario\test_authorized_keys"}[$id]
   if($id -eq 'A02'){if(-not[MailAccess]::CreateFile('mail.audit','MAIL01',$secrets.audit,$path)){throw 'Weak directory does not permit ordinary file creation'}}
   else{$access=if($id -eq 'A03'){[IO.FileAccess]::Read}else{[IO.FileAccess]::Write};if(-not[ForumNative]::CanOpen('mail.audit','MAIL01',$secrets.audit,$path,$access)){throw 'Weak ACL is not effective under ordinary token'}}
   Set-Control U02 $false
  }
  Set-Control $id $true;Assert-Control $id PASS repaired
  if($id -eq 'U01' -and [ForumNative]::Authenticate('mail.contractor','MAIL01',$secrets.contractor,2)){throw 'Protected unauthorized identity can authenticate'}
  if($id -like 'A*'){
   Set-Control U02 $true
   if($id -eq 'A02'){if([MailAccess]::CreateFile('mail.audit','MAIL01',$secrets.audit,$path)){throw 'Protected directory still permits ordinary file creation'}}
   else{$access=if($id -eq 'A03'){[IO.FileAccess]::Read}else{[IO.FileAccess]::Write};if([ForumNative]::CanOpen('mail.audit','MAIL01',$secrets.audit,$path,$access)){throw 'Protected ACL still grants prohibited access'};if($id -ne 'A03' -and -not[ForumNative]::CanOpen('mail.audit','MAIL01',$secrets.audit,$path,[IO.FileAccess]::Read)){throw 'Protected ordinary read lost'}}
   Set-Control U02 $false
  }
  Set-Control $id $false;Assert-Control $id FAIL final-planted;Assert-Business|Out-Null
 }
 Combined starting 0
 try{foreach($id in Get-ControlIds){Set-Control $id $true};Combined solution 100}finally{foreach($id in Get-ControlIds){Set-Control $id $false}}
 Combined restored 0;Phase guest-rehearsed
 $config=@('name = "summit-mail01"','title = "Summit Supply - Mail Server"','os = "Windows Server 2022 Datacenter"','user = "mail.fallback"','version = "2.1.1"','local = true','shell = false')
 foreach($c in $Controls){$config+=@('[[check]]',('message = "'+$c.policy.Replace('"','')+'"'),'points = 4','[[check.pass]]',"type = 'CommandOutput'",("cmd = '& powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\aeacus\probes\Probe.ps1 -Check "+$c.id+"'"),"value = 'PASS'")}
 $config|Set-Content "$root\scoring.conf" -Encoding ASCII;Copy-Item "$root\scoring.conf" C:\aeacus\scoring.conf
 'SUMMIT-MAIL01-PRACTICE'|Set-Content C:\aeacus\TeamID.txt -Encoding ASCII
 Push-Location C:\aeacus
 try{
  & .\aeacus.exe check|Out-Null;if($LASTEXITCODE){throw 'Aeacus check failed'}
  foreach($name in @('engine-starting','engine-solution','engine-restored')){
   $solution=($name -eq 'engine-solution');foreach($id in Get-ControlIds){Set-Control $id $solution}
   & .\aeacus.exe score|Out-Null;if($LASTEXITCODE){throw 'Native engine scoring failed'}
   $score=if($solution){100}else{0};$html=Get-Content .\assets\ScoringReport.html -Raw
   if($html -notmatch "(?<!\d)$score out of 100 points received" -or $html -notmatch '</html>'){throw "Engine score mismatch $name"}
   Copy-Item .\assets\ScoringReport.html "$root\$name.html";Assert-Business|Out-Null
  }
  & .\aeacus.exe encrypt|Out-Null;if($LASTEXITCODE -or (Get-Item .\scoring.dat).Length -eq 0){throw 'Encryption failed'}
  Remove-Item -LiteralPath C:\aeacus\scoring.conf;Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html
  $started=[DateTime]::UtcNow;New-Service CSSClient -BinaryPathName 'C:\aeacus\phocus.exe' -DisplayName 'Summit MAIL01 Competition Scoring' -StartupType Automatic|Out-Null;Start-Service CSSClient
  $deadline=(Get-Date).AddMinutes(4)
  do{Start-Sleep -Seconds 2;if((Get-Service CSSClient).Status -ne 'Running'){throw 'Production runtime stopped'};$fresh=$false;if(Test-Path .\assets\ScoringReport.html){$file=Get-Item .\assets\ScoringReport.html;$html=Get-Content $file.FullName -Raw;$fresh=($file.LastWriteTimeUtc -ge $started -and $html -match '(?<!\d)0 out of 100 points received' -and $html -match '</html>')}}until($fresh -or (Get-Date) -gt $deadline)
  if(-not$fresh){throw 'Fresh encrypted production report missing'}
 }finally{Pop-Location}
 Combined production 0
 foreach($c in $meta.issueManifest){$c.status='runtime-verified'};Save-Json $meta "$root\metadata.json"
 $receipt=[ordered]@{phase='runtime-verified';machine='MAIL01';root=$root;issues=25;points=100;startingScore=0;solutionScore=100;restoredScore=0;freshEncryptedReport=$true;probeHash=(Get-FileHash C:\aeacus\probes\Probe.ps1).Hash;configHash=(Get-FileHash "$root\scoring.conf").Hash;utc=[DateTime]::UtcNow.ToString('o');manualAcceptance='pending';export='not-performed';preservation=Assert-Business}
 Save-Json $receipt "$root\status.json";$receipt|ConvertTo-Json -Depth 5
}catch{
 $_|Out-String|Set-Content "$root\failure.txt";Phase failed
 try{Restore-Original}catch{$_|Out-String|Set-Content "$root\rollback-failure.txt";Phase recovery-needed}
 throw
}
