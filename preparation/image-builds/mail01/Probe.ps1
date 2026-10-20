param([string]$Check,[switch]$All)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
function Get-ControlIds {return @('U01','U02','S01','S02','S03','W01','W02','W03','W04','L01','L02','L03','P01','P02','P03','A01','A02','A03','A04','M01','M02','D01','O01','F01','F02')}
function Verdict($Value){if($null -eq $Value){return 'ERROR'};if($Value){return 'PASS'};return 'FAIL'}
function Scalar($Value){if($null -eq $Value){throw 'Missing native observation'};if($Value -is [string] -or $Value -is [bool] -or $Value -is [int] -or $Value -is [long]){return $Value};if($null -eq $Value.Value){throw 'Missing native attribute'};return $Value.Value}
function Test-ScenarioAcl([string]$Sddl,[string]$Policy){
 $acl=New-Object Security.AccessControl.FileSecurity;$acl.SetSecurityDescriptorSddlForm($Sddl)
 if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){return $false}
 $read=$false
 foreach($ace in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  $sid=$ace.IdentityReference.Value;$rights=[int64]$ace.FileSystemRights
  if($ace.AccessControlType -eq 'Deny'){if($sid -in @('S-1-5-18','S-1-5-32-544')){return $false};if($Policy -ne 'Private' -and $sid -in @('S-1-5-32-545','S-1-1-0','S-1-5-11') -and ($rights -band 0x90000001)){return $false};continue}
  if($sid -in @('S-1-5-18','S-1-5-32-544')){continue}
  if($Policy -eq 'Private'){if($rights -band 0xF00F01FF){return $false}}
  elseif($rights -band 0x500D0116){return $false}
  if($sid -eq 'S-1-5-32-545' -and ($rights -band 1)){$read=$true}
 }
 if($Policy -ne 'Private' -and -not $read){return $false};return $true
}
function Audit-Mask([string]$Guid){
 $out=& auditpol.exe /get /subcategory:$Guid /r
 if($LASTEXITCODE -ne 0){throw 'Native audit query failed'}
 $rows=@($out|ConvertFrom-Csv);if($rows.Count -ne 1){throw 'Unexpected audit output'}
 $setting=[string]$rows[0].'Inclusion Setting'
 switch($setting){'No Auditing'{return 0};'Success'{return 1};'Failure'{return 2};'Success and Failure'{return 3};default{throw 'Unsupported or unreadable native audit observation'}}
}
function Invoke-MailCheck([string]$Id,[string]$MetadataPath='C:\aeacus\probes\metadata.json'){
 try{
  if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
  $meta=Get-Content -LiteralPath $MetadataPath -Raw|ConvertFrom-Json;$pass=$null
  $public='C:\Users\Public\Documents\SummitMailCompetition';$scenario='C:\ProgramData\SummitMailScenario'
  switch($Id){
   'U01'{. "$PSScriptRoot\Native.ps1";$flags=[ForumNative]::UserFlags('mail.contractor');$pass=($flags -eq -1 -or ($flags -band 2))}
   'U02'{. "$PSScriptRoot\Native.ps1";$u=Get-LocalUser mail.audit;$pass=($u.Enabled -and $u.SID.Value -eq $meta.auditSid -and [ForumNative]::GroupSids('Administrators') -notcontains $u.SID.Value)}
   {$_ -like 'S*'}{
    $exe='C:\Windows\System32\OpenSSH\sshd.exe';if(-not(Test-Path $exe)){throw 'SSHD missing'}
    $service=Get-CimInstance Win32_Service -Filter "Name='sshd'";if($service.State -ne 'Running'){throw 'Required SSH service stopped'}
    $conf='C:\ProgramData\ssh\sshd_config'
    if((Get-Process -Id $service.ProcessId).StartTime.ToUniversalTime() -lt (Get-Item $conf).LastWriteTimeUtc){return 'FAIL'}
    $text=(& $exe -T -C 'user=administrator,host=mail01,addr=10.77.10.1'|Out-String);if($LASTEXITCODE -ne 0){throw 'SSHD effective configuration failed'}
    switch($Id){
     'S01'{$pass=($text -match '(?m)^permitemptypasswords no\r?$')}
     'S02'{$pass=($text -match '(?m)^disableforwarding yes\r?$' -or ($text -match '(?m)^allowtcpforwarding no\r?$' -and $text -match '(?m)^allowagentforwarding no\r?$' -and $text -match '(?m)^allowstreamlocalforwarding no\r?$'))}
     'S03'{$m=[regex]::Match($text,'(?m)^logingracetime (\d+)');if(-not$m.Success){throw 'Missing grace period'};$pass=([int]$m.Groups[1].Value -ge 1 -and [int]$m.Groups[1].Value -le 60)}
    }
   }
   {$_ -like 'W*'}{
    Import-Module WebAdministration;$site='IIS:\Sites\MailEnable WebMail';if(-not(Test-Path $site)){throw 'Required webmail missing'}
    switch($Id){
     'W01'{$pass=-not[bool](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/directoryBrowse -Name enabled))}
     'W02'{$pass=([string](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/httpErrors -Name errorMode)) -in @('Custom','DetailedLocalOnly'))}
     'W03'{$verbs=@(Get-WebConfiguration -PSPath $site -Filter system.webServer/security/requestFiltering/verbs/add);$pass=(@($verbs|Where-Object {$_.verb -eq 'TRACE' -and $_.allowed -eq $false}).Count -gt 0)}
     'W04'{$v=[long](Scalar(Get-WebConfigurationProperty -PSPath $site -Filter system.webServer/security/requestFiltering/requestLimits -Name maxAllowedContentLength));$pass=($v -ge 30000000 -and $v -le 50000000)}
    }
   }
   {$_ -like 'L*'}{$guid=@{L01='{0CCE922B-69AE-11D9-BED3-505054503030}';L02='{0CCE9235-69AE-11D9-BED3-505054503030}';L03='{0CCE9215-69AE-11D9-BED3-505054503030}'}[$Id];if(-not$guid){throw 'Unknown audit control'};$mask=Audit-Mask $guid;$pass=(($mask -band $(if($Id -eq 'L03'){2}else{1})) -ne 0)}
   'P01'{$r=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System';$pass=([string]$r.legalnoticecaption -match '\S' -and [string]$r.legalnoticetext -match '\S')}
   'P02'{$r=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System';$pass=($null -ne $r.InactivityTimeoutSecs -and $r.InactivityTimeoutSecs -ge 60 -and $r.InactivityTimeoutSecs -le 900)}
   'P03'{$r=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa';$pass=($r.RestrictAnonymousSAM -eq 1)}
   {$_ -like 'A*'}{
    $p=@{A01="$scenario\operations.ps1";A02="$scenario\Maintenance";A03="$scenario\confidential.txt";A04="$scenario\test_authorized_keys"}[$Id];if(-not$p -or -not(Test-Path -LiteralPath $p)){throw 'Required scenario resource absent'}
    $policy=if($Id -eq 'A03'){'Private'}else{'ReadOnly'}
    $pass=Test-ScenarioAcl (Get-Acl -LiteralPath $p).Sddl $policy
    if(-not(Test-ScenarioAcl (Get-Acl -LiteralPath $scenario).Sddl 'ReadOnly')){$pass=$false}
   }
   'M01'{$tasks=@(Get-ScheduledTask|Where-Object {($_.TaskPath -eq '\SummitMailScenario\' -and $_.TaskName -eq 'MailboxCacheSync') -or ($_.Actions.Arguments -match 'SummitMailScenario\\cache-marker\.cmd')});$pass=(@($tasks|Where-Object State -ne Disabled).Count -eq 0)}
   'M02'{$entries=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run').PSObject.Properties|Where-Object {$_.Name -notmatch '^PS' -and ($_.Name -eq 'SummitMailLegacy' -or [string]$_.Value -match 'SummitMailScenario\\startup-marker\.cmd')};$pass=(@($entries).Count -eq 0)}
   'D01'{$rules=@(Get-NetFirewallRule -PolicyStore ActiveStore -Name SummitMail-UnnecessaryIngress -ErrorAction SilentlyContinue);$pass=(@($rules|Where-Object {$_.Enabled -eq 'True' -and $_.Action -eq 'Allow' -and $_.Direction -eq 'Inbound'}).Count -eq 0)}
   'O01'{$svc=Get-Service wuauserv;$p=Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -ErrorAction SilentlyContinue;$pass=($svc.StartType -ne 'Disabled' -and ($null -eq $p -or $p.NoAutoUpdate -ne 1))}
   {$_ -in @('F01','F02')}{
    $scope="$public\Operations";if(-not(Test-Path $scope)){throw 'Required operations documents absent'}
    $hash=if($Id -eq 'F01'){$meta.credentialHash}else{$meta.archiveHash};if(-not$hash){throw 'Missing content fingerprint'};$pass=$true
    foreach($f in Get-ChildItem -LiteralPath $scope -File -Recurse -Force){if((Get-FileHash -LiteralPath $f.FullName).Hash -eq $hash){$pass=$false}}
   }
   default{throw 'Unknown control'}
  }
  return Verdict $pass
 }catch{return 'ERROR'}
}
if($Check){Invoke-MailCheck $Check}elseif($All){foreach($id in Get-ControlIds){[pscustomobject]@{id=$id;verdict=Invoke-MailCheck $id}}}
