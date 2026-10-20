param([ValidateSet('Prepare','Rehearse','Deploy')][string]$Stage='Prepare',[switch]$Resume)
#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'FORUM01'){throw 'This build is pinned to FORUM01'}
Import-Module WebAdministration
. "$PSScriptRoot\Answer.ps1"
. "$PSScriptRoot\Native.ps1"
$root='C:\ProgramData\SummitLab\ForumCompetition-20261004'
$public='C:\Users\Public\Documents\SummitCompetition'
$partner='C:\Users\Public\Documents\SummitPartner'
$scenario='C:\ProgramData\SummitScenario'
$appcmd="$env:windir\System32\inetsrv\appcmd.exe"
$ids=@('U01','U02','I01','I02','P01','P02','P03','P04','P05','A01','I03','I04','W01','S01','M01','F01','F02','Q01','Q02','Q03')
function Private-Directory([string]$Path) {
 New-Item -ItemType Directory -Path $Path | Out-Null
 & icacls.exe $Path /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Private directory ACL failed'}
}
function Save-Json($Value,[string]$Path){$Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8}
function New-Password {
 $bytes=New-Object byte[] 24;$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
 try{$rng.GetBytes($bytes);return 'Ex9!'+[Convert]::ToBase64String($bytes)}finally{$rng.Dispose()}
}
function Assert-Business {
 $r=Invoke-WebRequest http://127.0.0.1/ -UseBasicParsing -TimeoutSec 20
 if($r.StatusCode -ne 200 -or $r.Content -notmatch 'Summit Partner' -or $r.Content -match 'SQL ERROR'){throw 'Forum preservation failed'}
 foreach($name in @('W3SVC','FTPSVC','sshd')){if((Get-Service $name).Status -ne 'Running'){throw "Required service stopped: $name"}}
 if((Get-FileHash C:\FTP\Baseline\partner-info.txt).Hash -ne $meta.ftpFileHash){throw 'FTP business fixture changed'}
 if((Get-FileHash C:\inetpub\wwwroot\config.php).Hash -ne $meta.forumConfigHash){throw 'Forum business configuration changed'}
 foreach($user in @('Administrator','jwan5','ftp_reader','labadmin','forum.audit')){if(([ForumNative]::UserFlags($user) -band 2) -ne 0 -or [ForumNative]::UserFlags($user) -eq -1){throw "Required account unavailable: $user"}}
 $admins=[ForumNative]::GroupSids('Administrators')
 foreach($sid in @($meta.organizerSid,$meta.bootstrapSid,$meta.fallbackSid,$meta.domainAdminsSid)){if($admins -notcontains $sid){throw 'Required administrative access changed'}}
 if(-not[ForumNative]::Authenticate('labadmin',$env:COMPUTERNAME,$secrets.labadmin,2)){throw 'Fallback authentication failed'}
 if(-not[ForumNative]::Authenticate('forum.audit',$env:COMPUTERNAME,$secrets.audit,2)){throw 'Standard identity authentication failed'}
 [pscustomobject]@{forumStatus=200;requiredServices='running';businessHashes='unchanged';fallbackAuthentication=$true;standardAuthentication=$true}
}
function Set-Php([string]$Key,[string]$Value) {
 $path='C:\PHP\php.ini';$text=[IO.File]::ReadAllText($path)
 $regex='(?m)^\s*'+[regex]::Escape($Key)+'\s*=.*$'
 if([regex]::Matches($text,$regex).Count -ne 1){throw "PHP directive is ambiguous: $Key"}
 $text=[regex]::Replace($text,$regex,($Key+' = '+$Value));[IO.File]::WriteAllText($path,$text,[Text.Encoding]::ASCII)
}
function Set-Control([string]$Id,[bool]$Protected) {
 switch($Id) {
  'U01' {if($Protected){Disable-LocalUser -Name old.contractor}else{Enable-LocalUser -Name old.contractor}}
  'U02' {if($Protected){if([ForumNative]::GroupSids('Administrators') -contains $meta.auditSid){Remove-LocalGroupMember -Group Administrators -Member forum.audit}}else{if([ForumNative]::GroupSids('Administrators') -notcontains $meta.auditSid){Add-LocalGroupMember -Group Administrators -Member forum.audit}}}
  'I01' {Set-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/directoryBrowse -Name enabled -Value (-not $Protected)}
  'I02' {Set-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/httpErrors -Name errorMode -Value $(if($Protected){'Custom'}else{'Detailed'})}
  'P01' {Set-Php expose_php $(if($Protected){'Off'}else{'On'})}
  'P02' {Set-Php display_errors $(if($Protected){'Off'}else{'On'})}
  'P03' {Set-Php log_errors $(if($Protected){'On'}else{'Off'})}
  'P04' {Set-Php allow_url_include $(if($Protected){'Off'}else{'On'})}
  'P05' {Set-Php session.cookie_httponly $(if($Protected){'On'}else{'Off'})}
  'A01' {
   $path='C:\inetpub\wwwroot\config.php'
   $acl=New-Object Security.AccessControl.FileSecurity
   $acl.SetSecurityDescriptorSddlForm('O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;IS)(A;;FR;;;BU)')
   Set-Acl -LiteralPath $path -AclObject $acl
   if(-not $Protected){& icacls.exe $path /grant '*S-1-5-32-545:M' | Out-Null;if($LASTEXITCODE -ne 0){throw 'Weak ACL planting failed'}}
  }
  'I03' {Set-ItemProperty 'IIS:\Sites\Default Web Site' -Name logFile.enabled -Value $Protected}
  'I04' {Set-ItemProperty 'IIS:\Sites\Summit Baseline FTP' -Name ftpServer.logFile.enabled -Value $Protected}
  'W01' {Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name UserAuthentication -Value ([int]$Protected)}
  'S01' {if($Protected){Stop-Service RemoteRegistry;Set-Service RemoteRegistry -StartupType Disabled}else{Set-Service RemoteRegistry -StartupType Automatic;Start-Service RemoteRegistry}}
  'M01' {
   if($Protected){$t=Get-ScheduledTask -TaskPath '\SummitScenario\' -TaskName PartnerCacheSync -ErrorAction SilentlyContinue;if($t){Unregister-ScheduledTask -InputObject $t -Confirm:$false};if(Test-Path "$scenario\partner-cache.cmd"){Remove-Item -LiteralPath "$scenario\partner-cache.cmd"}}
   else {
    Copy-Item "$root\fixtures\partner-cache.cmd" "$scenario\partner-cache.cmd" -Force
    $action=New-ScheduledTaskAction -Execute 'C:\Windows\System32\cmd.exe' -Argument '/d /c "C:\ProgramData\SummitScenario\partner-cache.cmd"'
    $principal=New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount -RunLevel Limited
    $trigger=New-ScheduledTaskTrigger -AtLogOn
    $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskPath '\SummitScenario\' -TaskName PartnerCacheSync -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Description 'Synthetic competition incident: harmless local marker only' -Force | Out-Null
   }
  }
  'F01' {if($Protected){if(Test-Path "$partner\contractor-notes.txt"){Remove-Item -LiteralPath "$partner\contractor-notes.txt"}}else{Copy-Item "$root\fixtures\contractor-notes.txt" "$partner\contractor-notes.txt" -Force}}
  'F02' {if($Protected){if(Test-Path "$partner\personal-media.zip"){Remove-Item -LiteralPath "$partner\personal-media.zip"}}else{Copy-Item "$root\fixtures\personal-media.zip" "$partner\personal-media.zip" -Force}}
  {$_ -in @('Q01','Q02','Q03')} {
   $number=[int]$Id.Substring(1);$text=[IO.File]::ReadAllText("$root\fixtures\question-$number.txt")
   if($Protected){$text+=$secrets.answers[$number-1]+"`r`n"}
   [IO.File]::WriteAllText("$public\Forensic Question $number.txt",$text,[Text.Encoding]::UTF8)
  }
  default {throw 'Unknown control'}
 }
}
function Restart-Php {Restart-WebAppPool DefaultAppPool}
function Restore-Challenge {
 $failed=@()
 # Clear public answers first, even when another restoration later fails.
 foreach($id in @('Q01','Q02','Q03')+@($ids | Where-Object {$_ -notlike 'Q*'})) {
  try {Set-Control $id $false}catch{$failed+="$id : $($_.Exception.Message)"}
 }
 try {Restart-Php}catch{$failed+=$_.Exception.Message}
 if($failed.Count){Save-Json ([ordered]@{phase='recovery-needed';failures=$failed;utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json";throw 'Challenge restoration failed; consult preserved recovery evidence'}
}
function Assert-Control([string]$Id,[string]$Expected,[string]$State) {
 $observed=Invoke-ForumCheck $Id
 if($observed -ne $Expected){throw "$Id in ${State}: expected $Expected, observed $observed"}
 $record=[pscustomobject]@{id=$Id;state=$State;verdict=$observed;utc=[DateTime]::UtcNow.ToString('o')}
 $record | ConvertTo-Json -Compress | Add-Content "$root\matrix.jsonl" -Encoding UTF8
 Write-Output "$Id $State $observed"
}
function Assert-Combined([string]$Name,[int]$Expected) {
 $results=@(foreach($id in $ids){[pscustomobject]@{id=$id;verdict=Invoke-ForumCheck $id}})
 if(@($results | Where-Object verdict -eq ERROR).Count){throw "$Name contains probe errors"}
 $points=5*@($results | Where-Object verdict -eq PASS).Count
 if($points -ne $Expected){throw "$Name score $points/$Expected"}
 Save-Json ([ordered]@{name=$Name;points=$points;results=$results;preservation=Assert-Business;utc=[DateTime]::UtcNow.ToString('o')}) "$root\$Name.json"
 Write-Output "$Name $points/100"
}
if($Stage -eq 'Prepare') {
 if(Test-Path $root){throw 'Existing recovery record: diagnose or recover; never overwrite it'}
 foreach($path in @($public,$partner,$scenario,'C:\aeacus\probes')){if(Test-Path $path){throw "Unexpected existing scenario path: $path"}}
 if(Get-Service CSSClient -ErrorAction SilentlyContinue){throw 'Existing scorer requires a separately reviewed cutover'}
 foreach($name in @('labadmin','forum.audit','old.contractor')){if([ForumNative]::UserFlags($name) -ne -1){throw "Existing identity conflict: $name"}}
 if((Get-CimInstance Win32_ComputerSystem).Domain -ne 'corp.summit.test'){throw 'Domain mismatch'}
 $response=Invoke-WebRequest http://127.0.0.1/ -UseBasicParsing -TimeoutSec 20
 if($response.StatusCode -ne 200 -or $response.Content -notmatch 'Summit Partner'){throw 'Business baseline failed'}
 Private-Directory $root
 Private-Directory "$root\backup"
 Private-Directory "$root\fixtures"
 Save-Json ([ordered]@{phase='backing-up';utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json"
 $original=[ordered]@{
  machine=$env:COMPUTERNAME;domain='corp.summit.test';snapshot='Clean-Before-Competition-20261004'
  configSddl=(Get-Acl C:\inetpub\wwwroot\config.php).Sddl
  phpSddl=(Get-Acl C:\PHP\php.ini).Sddl
  webConfigSddl=(Get-Acl C:\inetpub\wwwroot\web.config).Sddl
  directoryBrowsing=(Get-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/directoryBrowse -Name enabled).Value
  errorMode=[string](Get-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/httpErrors -Name errorMode)
  webLogging=[bool](Get-Item 'IIS:\Sites\Default Web Site').logFile.enabled
  ftpLogging=[bool](Get-Item 'IIS:\Sites\Summit Baseline FTP').ftpServer.logFile.enabled
  nla=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp').UserAuthentication
  remoteRegistry=Get-CimInstance Win32_Service -Filter "Name='RemoteRegistry'" | Select-Object State,StartMode
  aeacusHash=(Get-FileHash C:\aeacus\aeacus.exe).Hash;phocusHash=(Get-FileHash C:\aeacus\phocus.exe).Hash
 }
 Copy-Item C:\PHP\php.ini "$root\backup\php.ini"
 Copy-Item C:\inetpub\wwwroot\config.php "$root\backup\config.php"
 Copy-Item C:\inetpub\wwwroot\web.config "$root\backup\web.config"
 Copy-Item C:\Windows\System32\inetsrv\config\applicationHost.config "$root\backup\applicationHost.config"
 Save-Json $original "$root\backup\original.json"
 Copy-Item "$PSScriptRoot\Recover-Competition.ps1" "$root\backup\Recover-Competition.ps1"
 Compress-Archive -Path "$root\backup\*" -DestinationPath "$root\prebuild-recovery.zip"
 Write-Output 'BACKUP_READY: download prebuild-recovery.zip before preparing accounts'
 Save-Json ([ordered]@{phase='backup-ready';utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json"
 exit
}
if(-not(Test-Path "$root\status.json")){throw 'Prepared recovery record missing'}
$status=Get-Content "$root\status.json" -Raw | ConvertFrom-Json
if($Stage -eq 'Rehearse') {
 if($status.phase -eq 'backup-ready') {
 Save-Json ([ordered]@{phase='preparing-scenario';utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json"
 $secrets=[ordered]@{labadmin=New-Password;audit=New-Password;contractor=New-Password;answers=@()}
 Save-Json $secrets "$root\secrets.json"
 foreach($record in @(@{name='labadmin';key='labadmin'},@{name='forum.audit';key='audit'},@{name='old.contractor';key='contractor'})) {
  $pw=ConvertTo-SecureString $secrets[$record.key] -AsPlainText -Force
  New-LocalUser -Name $record.name -Password $pw -Disabled -Description 'Summit Supply competition local identity' | Out-Null
 }
 Add-LocalGroupMember -Group Administrators -Member labadmin
 Add-LocalGroupMember -Group Users -Member forum.audit,old.contractor
 Enable-LocalUser labadmin;Enable-LocalUser forum.audit
 $localPrefix=([Security.Principal.NTAccount]::new($env:COMPUTERNAME,'Administrator').Translate([Security.Principal.SecurityIdentifier]).Value) -replace '-500$',''
 $meta=[ordered]@{buildId='forum01-20261004';expectedStart=0;expectedSolution=100;issueCount=20;points=100;organizerSid="$localPrefix-500";bootstrapSid="$localPrefix-1000";domainAdminsSid='S-1-5-21-1538098495-642441483-3435665723-512';fallbackSid=([Security.Principal.NTAccount]::new($env:COMPUTERNAME,'labadmin').Translate([Security.Principal.SecurityIdentifier]).Value);auditSid=([Security.Principal.NTAccount]::new($env:COMPUTERNAME,'forum.audit').Translate([Security.Principal.SecurityIdentifier]).Value);contractorSid=([Security.Principal.NTAccount]::new($env:COMPUTERNAME,'old.contractor').Translate([Security.Principal.SecurityIdentifier]).Value);forumConfigHash=(Get-FileHash C:\inetpub\wwwroot\config.php).Hash;ftpFileHash=(Get-FileHash C:\FTP\Baseline\partner-info.txt).Hash;answerHashes=@();prohibitedCredentialHash='';prohibitedArchiveHash=''}
 Save-Json $meta "$root\metadata.json"
 Assert-Business | Out-Null
 foreach($path in @($public,$partner,$scenario)){New-Item -ItemType Directory -Path $path | Out-Null}
 & icacls.exe $scenario /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-19:(OI)(CI)RX' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Inert payload directory ACL failed'}
 New-Item -ItemType File "$scenario\marker.txt" | Out-Null
 & icacls.exe "$scenario\marker.txt" /grant '*S-1-5-19:M' | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Marker ACL failed'}
 $payload="@echo off`r`necho SIMULATION ONLY - FORUM01 - $([guid]::NewGuid())>> C:\ProgramData\SummitScenario\marker.txt`r`n"
 [IO.File]::WriteAllText("$root\fixtures\partner-cache.cmd",$payload,[Text.Encoding]::ASCII)
 New-Item -ItemType Directory "$public\Evidence" | Out-Null
 Copy-Item "$root\fixtures\partner-cache.cmd" "$public\Evidence\retained-payload.cmd"
 @('Synthetic incident evidence for this competition; this is a retained training record.','2026-10-04T14:00:00-06:00 actor=FORUM01\forum.audit operation=change-file-permissions target=C:\inetpub\wwwroot\config.php','2026-10-04T14:03:00-06:00 actor=FORUM01\forum.audit operation=register-task task=\SummitScenario\PartnerCacheSync payload=C:\ProgramData\SummitScenario\partner-cache.cmd') | Set-Content "$public\Evidence\incident-audit.txt" -Encoding UTF8
 $secrets.answers=@('forum01\forum.audit','\summitscenario\partnercachesync',(Get-FileHash "$root\fixtures\partner-cache.cmd").Hash.ToLowerInvariant())
 $meta.answerHashes=@($secrets.answers | ForEach-Object {Get-TextHash $_})
 $questions=@(
  @{question='Which account changed the forum configuration permissions in the supplied incident record?';format='MACHINE\username, case insensitive';evidence='incident-audit.txt'},
  @{question='What is the full scheduled-task path used for persistence in the supplied incident record?';format='Full task path beginning with a backslash, case insensitive';evidence='incident-audit.txt'},
  @{question='What is the SHA-256 hash of the retained inert payload?';format='64 hexadecimal characters, case insensitive';evidence='retained-payload.cmd'}
 )
 for($i=0;$i -lt 3;$i++) {
  $q=$questions[$i];$number=$i+1
  $text="Forensic Question $number`r`n`r`nQuestion: $($q.question)`r`nEvidence: $public\Evidence\$($q.evidence)`r`nAnswer format: $($q.format)`r`n`r`nAnswer:`r`n"
  [IO.File]::WriteAllText("$root\fixtures\question-$number.txt",$text,[Text.Encoding]::UTF8)
  Copy-Item "$root\fixtures\question-$number.txt" "$public\Forensic Question $number.txt"
  & icacls.exe "$public\Forensic Question $number.txt" /grant '*S-1-5-32-545:M' | Out-Null
  if($LASTEXITCODE -ne 0){throw 'Answer file write ACL failed'}
 }
 @('FICTIONAL-TRAINING-CREDENTIALS','This file contains exercise-only secrets, never real credentials.',"partner_token=EXERCISE-$([guid]::NewGuid())") | Set-Content "$root\fixtures\contractor-notes.txt" -Encoding ASCII
 'Synthetic personal media list. Unauthorized on this business server.' | Set-Content "$root\fixtures\private-movie-list.txt" -Encoding ASCII
 Compress-Archive -LiteralPath "$root\fixtures\private-movie-list.txt" -DestinationPath "$root\fixtures\personal-media.zip"
 $meta.prohibitedCredentialHash=(Get-FileHash "$root\fixtures\contractor-notes.txt").Hash
 $meta.prohibitedArchiveHash=(Get-FileHash "$root\fixtures\personal-media.zip").Hash
 'Summit Supply partner support documents belong in this directory. Preserve this file.' | Set-Content "$partner\partner-business.txt" -Encoding UTF8
 New-Item -ItemType Directory C:\aeacus\probes | Out-Null
 & icacls.exe C:\aeacus\probes /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Probe ACL failed'}
 Copy-Item "$PSScriptRoot\Probe.ps1","$PSScriptRoot\Answer.ps1","$PSScriptRoot\Native.ps1" C:\aeacus\probes
 Save-Json $meta "$root\metadata.json";Save-Json $meta C:\aeacus\probes\metadata.json;Save-Json $secrets "$root\secrets.json"
 Copy-Item "$root\metadata.json" "$root\backup\metadata.json"
 Copy-Item "$PSScriptRoot\README.html" "$public\README.html"
 $shell=New-Object -ComObject WScript.Shell
 foreach($entry in @(@{name='Summit Competition README';path="$public\README.html"},@{name='Summit Scoring Report';path='C:\aeacus\assets\ScoringReport.html'},@{name='Forensic Question 1';path="$public\Forensic Question 1.txt"},@{name='Forensic Question 2';path="$public\Forensic Question 2.txt"},@{name='Forensic Question 3';path="$public\Forensic Question 3.txt"})) {
  $link=$shell.CreateShortcut("C:\Users\Public\Desktop\$($entry.name).lnk");$link.TargetPath=$entry.path;$link.Save()
 }
 . C:\aeacus\probes\Probe.ps1
 Save-Json ([ordered]@{phase='rehearsing';utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json"
 } elseif($Resume -and $status.phase -in @('rehearsing','guest-rehearsed')) {
  $meta=Get-Content "$root\metadata.json" -Raw | ConvertFrom-Json
  $secrets=Get-Content "$root\secrets.json" -Raw | ConvertFrom-Json
  foreach($entry in @(@{name='labadmin';sid=$meta.fallbackSid},@{name='forum.audit';sid=$meta.auditSid},@{name='old.contractor';sid=$meta.contractorSid})) {
   $sid=([Security.Principal.NTAccount]::new($env:COMPUTERNAME,$entry.name).Translate([Security.Principal.SecurityIdentifier]).Value)
   if($sid -ne $entry.sid){throw 'Interrupted identity does not match recovery record'}
  }
  foreach($path in @("$root\backup\original.json","$root\fixtures\partner-cache.cmd",'C:\aeacus\probes\metadata.json',"$public\Forensic Question 1.txt")){if(-not(Test-Path $path)){throw 'Interrupted build prerequisites incomplete'}}
  Copy-Item "$PSScriptRoot\Probe.ps1","$PSScriptRoot\Answer.ps1","$PSScriptRoot\Native.ps1" C:\aeacus\probes -Force
  if(-not(Test-Path "$root\backup\metadata.json")){Copy-Item "$root\metadata.json" "$root\backup\metadata.json"}
  . C:\aeacus\probes\Probe.ps1
  Assert-Business | Out-Null
  Save-Json ([ordered]@{phase='rehearsing';utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json"
  Write-Output 'Verified known interrupted rehearsal state; restarting all control matrices with corrected probe'
 } else {throw 'Rehearsal cannot resume an unrecognized state'}
 foreach($id in $ids) {
  Set-Control $id $true;if($id -like 'P*'){Restart-Php}
  Assert-Control $id PASS protected
  Set-Control $id $false;if($id -like 'P*'){Restart-Php}
  Assert-Control $id FAIL planted
  if($id -eq 'U01') {if(-not[ForumNative]::Authenticate('old.contractor',$env:COMPUTERNAME,$secrets.contractor,2)){throw 'Planted unauthorized account is not actually interactive'}}
  if($id -eq 'A01') {
   # Use the retained standard identity after removing its temporary administrative grant.
   Set-Control U02 $true
   if(-not[ForumNative]::CanOpen('forum.audit',$env:COMPUTERNAME,$secrets.audit,'C:\inetpub\wwwroot\config.php',[IO.FileAccess]::Write)){throw 'Planted config ACL is not effectively writable'}
   Set-Control U02 $false
  }
  if($id -eq 'M01') {
   Start-ScheduledTask -TaskPath '\SummitScenario\' -TaskName PartnerCacheSync
   $deadline=(Get-Date).AddSeconds(20)
   do{Start-Sleep -Milliseconds 500;$info=Get-ScheduledTaskInfo -TaskPath '\SummitScenario\' -TaskName PartnerCacheSync}until(($info.LastRunTime.Year -gt 2000 -and $info.LastTaskResult -ne 267009) -or (Get-Date) -gt $deadline)
   if($info.LastTaskResult -ne 0 -or (Get-Content "$scenario\marker.txt" -Raw) -notmatch 'SIMULATION ONLY'){throw 'Inert task execution failed'}
   Export-ScheduledTask -TaskPath '\SummitScenario\' -TaskName PartnerCacheSync | Set-Content "$public\Evidence\retained-task.xml" -Encoding UTF8
  }
  Set-Control $id $true;if($id -like 'P*'){Restart-Php}
  Assert-Control $id PASS repaired
  if($id -eq 'U01') {if([ForumNative]::Authenticate('old.contractor',$env:COMPUTERNAME,$secrets.contractor,2)){throw 'Disabled unauthorized identity can still authenticate'}}
  if($id -eq 'A01') {
   Set-Control U02 $true
   if([ForumNative]::CanOpen('forum.audit',$env:COMPUTERNAME,$secrets.audit,'C:\inetpub\wwwroot\config.php',[IO.FileAccess]::Write)){throw 'Protected config remains effectively writable'}
   if(-not[ForumNative]::CanOpen('forum.audit',$env:COMPUTERNAME,$secrets.audit,'C:\inetpub\wwwroot\config.php',[IO.FileAccess]::Read)){throw 'Standard read access lost'}
   Set-Control U02 $false
  }
  Set-Control $id $false;if($id -like 'P*'){Restart-Php}
  Assert-Control $id FAIL final-planted
  Assert-Business | Out-Null
 }
 Assert-Combined starting 0
 try {foreach($id in $ids){Set-Control $id $true};Restart-Php;Assert-Combined solution 100}
 finally {Restore-Challenge}
 Assert-Combined restored 0
 Save-Json ([ordered]@{phase='guest-rehearsed';utc=[DateTime]::UtcNow.ToString('o')}) "$root\status.json"
 exit
}
if($Stage -eq 'Deploy') {
 if($status.phase -ne 'guest-rehearsed'){throw 'Guest rehearsals must pass before deployment'}
 $meta=Get-Content "$root\metadata.json" -Raw | ConvertFrom-Json
 $secrets=Get-Content "$root\secrets.json" -Raw | ConvertFrom-Json
 . C:\aeacus\probes\Probe.ps1
 Assert-Combined predeployment 0
 Copy-Item "$PSScriptRoot\scoring.conf" C:\aeacus\scoring.conf
 'SUMMIT-FORUM01-PRACTICE' | Set-Content C:\aeacus\TeamID.txt -Encoding ASCII
 Push-Location C:\aeacus
 try {
  & .\aeacus.exe check | Out-Null;if($LASTEXITCODE -ne 0){throw 'Aeacus validation failed'}
  & .\aeacus.exe score | Out-Null;if($LASTEXITCODE -ne 0){throw 'Aeacus starting score failed'}
  $report=Get-Content .\assets\ScoringReport.html -Raw
  if($report -notmatch '0 out of 100 points received'){throw 'Aeacus starting score is wrong'}
  # A full solution is scored by the real engine before restoring the challenge.
  try {
   foreach($id in $ids){Set-Control $id $true};Restart-Php
   & .\aeacus.exe score | Out-Null;if($LASTEXITCODE -ne 0){throw 'Aeacus solution scoring failed'}
   $report=Get-Content .\assets\ScoringReport.html -Raw
   if($report -notmatch '100 out of 100 points received'){throw 'Aeacus solution score is wrong'}
   Assert-Business | Out-Null
  } finally {Restore-Challenge}
  & .\aeacus.exe score | Out-Null;if($LASTEXITCODE -ne 0){throw 'Aeacus restored scoring failed'}
  $report=Get-Content .\assets\ScoringReport.html -Raw
  if($report -notmatch '0 out of 100 points received'){throw 'Aeacus restored score is wrong'}
  & .\aeacus.exe encrypt | Out-Null;if($LASTEXITCODE -ne 0 -or (Get-Item .\scoring.dat).Length -eq 0){throw 'Encrypted configuration failed'}
  & icacls.exe .\scoring.dat /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' | Out-Null
  if($LASTEXITCODE -ne 0){throw 'Encrypted configuration ACL failed'}
  Remove-Item -LiteralPath C:\aeacus\scoring.conf
  Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html
  $started=[DateTime]::UtcNow
  New-Service -Name CSSClient -BinaryPathName 'C:\aeacus\phocus.exe' -DisplayName 'Summit Forum Competition Scoring' -StartupType Automatic | Out-Null
  Start-Service CSSClient
  $deadline=(Get-Date).AddMinutes(4)
  do {
   Start-Sleep -Seconds 2
   if((Get-Service CSSClient).Status -ne 'Running'){throw 'Encrypted runtime stopped'}
   $fresh=$false
   if(Test-Path C:\aeacus\assets\ScoringReport.html){$file=Get-Item C:\aeacus\assets\ScoringReport.html;$html=Get-Content $file.FullName -Raw;$fresh=($file.LastWriteTimeUtc -ge $started -and $html -match '0 out of 100 points received' -and $html -match '</html>')}
  } until($fresh -or (Get-Date) -gt $deadline)
  if(-not $fresh){throw 'Fresh encrypted runtime report not proven'}
  $receipt=[ordered]@{phase='runtime-verified';machine='FORUM01';issues=20;points=100;startingScore=0;solutionScore=100;restoredScore=0;encryptedReportFresh=$true;serviceStatus=[string](Get-Service CSSClient).Status;serviceStartup=[string](Get-Service CSSClient).StartType;probeHash=(Get-FileHash C:\aeacus\probes\Probe.ps1).Hash;configHash=(Get-FileHash "$PSScriptRoot\scoring.conf").Hash;reportUtc=$file.LastWriteTimeUtc.ToString('o');manualAcceptance='pending';export='not-requested';preservation=Assert-Business}
  Save-Json $receipt "$root\status.json"
  $receipt | ConvertTo-Json -Depth 5
 } finally {Pop-Location}
}
