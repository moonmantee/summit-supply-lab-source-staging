param([Parameter(Mandatory)][string]$RecoveryDirectory)
#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'FORUM01'){throw 'Recovery is pinned to FORUM01'}
$backup=(Resolve-Path -LiteralPath $RecoveryDirectory).Path
$original=Get-Content -LiteralPath (Join-Path $backup 'original.json') -Raw | ConvertFrom-Json
if($original.machine -ne 'FORUM01' -or $original.domain -ne 'corp.summit.test'){throw 'Recovery identity mismatch'}
foreach($name in @('php.ini','config.php','web.config','applicationHost.config')){if(-not(Test-Path -LiteralPath (Join-Path $backup $name))){throw 'Incomplete recovery archive'}}
$errorMode=$original.errorMode
if(-not $errorMode){
 $correction=Get-Content (Join-Path $backup 'original-error-mode-correction.json') -Raw | ConvertFrom-Json
 if($correction.errorMode -ne 'DetailedLocalOnly' -or $correction.evidence -ne 'immutable config has no override; installed IIS schema default'){throw 'Unrecognized recovery correction'}
 if((Get-FileHash (Join-Path $backup 'applicationHost.config')).Hash -ne $correction.sourceApphostHash -or (Get-FileHash (Join-Path $backup 'web.config')).Hash -ne $correction.sourceWebConfigHash){throw 'Recovery correction source hash mismatch'}
 $errorMode=$correction.errorMode
}
if($errorMode -notin @('Custom','Detailed','DetailedLocalOnly')){throw 'Invalid saved IIS error mode'}
# Validate every owned PHP merge and the saved ACL before any recovery mutation.
$live=[IO.File]::ReadAllText('C:\PHP\php.ini');$saved=[IO.File]::ReadAllText((Join-Path $backup 'php.ini'))
foreach($key in @('expose_php','display_errors','log_errors','allow_url_include','session.cookie_httponly')){
 $pattern='(?m)^\s*'+[regex]::Escape($key)+'\s*=.*$'
 $match=[regex]::Match($saved,$pattern)
 if(-not $match.Success -or [regex]::Matches($live,$pattern).Count -ne 1){throw 'PHP recovery directive mismatch'}
 $live=[regex]::Replace($live,$pattern,$match.Value)
}
$acl=New-Object Security.AccessControl.FileSecurity;$acl.SetSecurityDescriptorSddlForm($original.configSddl)
Import-Module WebAdministration
$service=Get-CimInstance Win32_Service -Filter "Name='CSSClient'"
if($service){
 if($service.PathName -ne 'C:\aeacus\phocus.exe'){throw 'Unexpected scoring service; recovery stopped'}
 Stop-Service CSSClient
 & sc.exe delete CSSClient | Out-Null
 if($LASTEXITCODE -ne 0){throw 'Could not remove owned scorer'}
}
$task=Get-ScheduledTask -TaskPath '\SummitScenario\' -TaskName PartnerCacheSync -ErrorAction SilentlyContinue
if($task){Unregister-ScheduledTask -InputObject $task -Confirm:$false}
Set-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/directoryBrowse -Name enabled -Value $original.directoryBrowsing
Set-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/httpErrors -Name errorMode -Value $errorMode
Set-ItemProperty 'IIS:\Sites\Default Web Site' -Name logFile.enabled -Value $original.webLogging
Set-ItemProperty 'IIS:\Sites\Summit Baseline FTP' -Name ftpServer.logFile.enabled -Value $original.ftpLogging
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name UserAuthentication -Value $original.nla
# Merge only the five owned PHP directives, preserving unrelated changes.
[IO.File]::WriteAllText('C:\PHP\php.ini',$live,[Text.Encoding]::ASCII)
Set-Acl C:\inetpub\wwwroot\config.php $acl
if($original.remoteRegistry.StartMode -eq 'Auto'){Set-Service RemoteRegistry -StartupType Automatic}elseif($original.remoteRegistry.StartMode -eq 'Manual'){Set-Service RemoteRegistry -StartupType Manual}else{Set-Service RemoteRegistry -StartupType Disabled}
if($original.remoteRegistry.State -eq 'Running'){Start-Service RemoteRegistry}else{Stop-Service RemoteRegistry}
# Scenario accounts are removed only when the saved SIDs identify this build.
$metadataPath=Join-Path $backup 'metadata.json'
if(Test-Path $metadataPath){
 $meta=Get-Content $metadataPath -Raw | ConvertFrom-Json
 foreach($entry in @(@{name='labadmin';sid=$meta.fallbackSid},@{name='forum.audit';sid=$meta.auditSid},@{name='old.contractor';sid=$meta.contractorSid})){
  $user=Get-LocalUser -Name $entry.name -ErrorAction SilentlyContinue
  if($user){if($user.SID.Value -ne $entry.sid){throw 'Scenario identity SID mismatch'};Remove-LocalUser -SID $user.SID}
 }
}
Restart-WebAppPool DefaultAppPool
$response=Invoke-WebRequest http://127.0.0.1/ -UseBasicParsing -TimeoutSec 20
if($response.StatusCode -ne 200 -or $response.Content -notmatch 'Summit Partner'){throw 'Recovered forum failed validation'}
foreach($name in @('W3SVC','FTPSVC','sshd')){if((Get-Service $name).Status -ne 'Running'){throw 'Recovered required service failed'}}
'Recovered owned security settings; participant documents retained. Consult the clean snapshot for full pre-build restoration.'
