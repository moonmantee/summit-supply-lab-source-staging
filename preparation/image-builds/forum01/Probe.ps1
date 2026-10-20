param([string]$Check,[switch]$All)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
. "$PSScriptRoot\Answer.ps1"
function Get-IisValue($Value) {
 if($Value -is [string] -or $Value -is [bool] -or $Value -is [int]){return $Value}
 if($null -eq $Value -or $null -eq $Value.Value){throw 'Unreadable IIS attribute'}
 return $Value.Value
}
function Get-ForumVerdict($Observation) {
 if($null -eq $Observation){return 'ERROR'}
 if($Observation){return 'PASS'}
 return 'FAIL'
}
function Test-ConfigAcl([string]$Sddl) {
 $acl=New-Object Security.AccessControl.FileSecurity
 $acl.SetSecurityDescriptorSddlForm($Sddl)
 $owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
 if($owner -notin @('S-1-5-18','S-1-5-32-544')){return $false}
 $reader=$false;$ordinaryReader=$false
 foreach($ace in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
  $sid=$ace.IdentityReference.Value;$rights=[int64]$ace.FileSystemRights
  # This policy requires ordinary-user and application reading; read-denial ACLs cannot satisfy it.
  if($ace.AccessControlType -eq 'Deny') {if($rights -band 0x90000001){return $false};continue}
  if($sid -eq 'S-1-5-32-568' -and ($rights -band 1)){$reader=$true}
  if($sid -eq 'S-1-5-32-545' -and ($rights -band 1)){$ordinaryReader=$true}
  if(($rights -band 0x500D0116) -and $sid -notin @('S-1-5-18','S-1-5-32-544','S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')){return $false}
 }
 return ($reader -and $ordinaryReader)
}
function Invoke-ForumCheck([string]$Id,[string]$MetadataPath='C:\aeacus\probes\metadata.json') {
 try {
  $meta=Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
  if($env:COMPUTERNAME -ne 'FORUM01'){throw 'Wrong guest'}
  $pass=$null
  switch($Id) {
   'U01' {. "$PSScriptRoot\Native.ps1";$flags=[ForumNative]::UserFlags('old.contractor');$pass=($flags -eq -1 -or ($flags -band 2) -ne 0)}
   'U02' {
    . "$PSScriptRoot\Native.ps1";$flags=[ForumNative]::UserFlags('forum.audit')
    if($flags -eq -1){$pass=$false}else{
     $currentSid=([Security.Principal.NTAccount]::new($env:COMPUTERNAME,'forum.audit').Translate([Security.Principal.SecurityIdentifier]).Value)
     $pass=($currentSid -eq $meta.auditSid -and ($flags -band 2) -eq 0 -and [ForumNative]::GroupSids('Administrators') -notcontains $currentSid)
    }
   }
   {$_ -in @('I01','I02','I03','I04')} {
    Import-Module WebAdministration
    if(-not(Test-Path IIS:\Sites\'Default Web Site') -or -not(Test-Path IIS:\Sites\'Summit Baseline FTP')){throw 'Required site absent'}
    switch($Id) {
     'I01' {$pass=-not [bool](Get-IisValue (Get-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/directoryBrowse -Name enabled))}
     'I02' {$pass=([string](Get-IisValue (Get-WebConfigurationProperty -PSPath 'IIS:\Sites\Default Web Site' -Filter system.webServer/httpErrors -Name errorMode)) -eq 'Custom')}
     'I03' {$pass=[bool](Get-Item 'IIS:\Sites\Default Web Site').logFile.enabled}
     'I04' {$pass=[bool](Get-Item 'IIS:\Sites\Summit Baseline FTP').ftpServer.logFile.enabled}
    }
   }
   {$_ -in @('P01','P02','P03','P04','P05')} {
    foreach($path in @('C:\PHP\php.exe','C:\PHP\php-cgi.exe','C:\PHP\php.ini')){if(-not(Test-Path $path -PathType Leaf)){throw 'Required PHP component missing'}}
    $info=(& C:\PHP\php.exe -c C:\PHP\php.ini -i | Out-String)
    if($LASTEXITCODE -ne 0){throw 'PHP effective configuration failed'}
    $key=@{P01='expose_php';P02='display_errors';P03='log_errors';P04='allow_url_include';P05='session.cookie_httponly'}[$Id]
    $m=[regex]::Match($info,'(?m)^'+[regex]::Escape($key)+' => (\S+) =>')
    if(-not $m.Success){throw 'Missing PHP observation'}
    $expect=@{P01='Off';P02='Off';P03='On';P04='Off';P05='On'}[$Id]
    $pass=($m.Groups[1].Value -eq $expect)
    # Per-directory and IIS environment overrides are not silently ignored.
    if(@(Get-ChildItem C:\inetpub\wwwroot -Filter .user.ini -Recurse -Force).Count -gt 0){$pass=$false}
    Import-Module WebAdministration
    $cgi=Get-WebConfiguration -PSPath IIS:\ -Filter system.webServer/fastCgi/application
    $php=@($cgi | Where-Object fullPath -eq 'C:\PHP\php-cgi.exe')
    if($php.Count -ne 1){throw 'Unexpected PHP activation'}
    if($php[0].arguments -or @($php[0].environmentVariables.Collection | Where-Object name -in @('PHPRC','PHP_INI_SCAN_DIR')).Count){$pass=$false}
   }
   'A01' {
    $path='C:\inetpub\wwwroot\config.php'
    if(-not(Test-Path $path)){throw 'Required forum configuration missing'}
    if((Get-FileHash $path -Algorithm SHA256).Hash -ne $meta.forumConfigHash){$pass=$false}else{$pass=Test-ConfigAcl (Get-Acl $path).Sddl}
   }
   'W01' {$value=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp';$pass=($value.UserAuthentication -eq 1)}
   'S01' {$service=Get-CimInstance Win32_Service -Filter "Name='RemoteRegistry'";if(-not $service){throw 'Service query failed'};$pass=($service.State -eq 'Stopped' -and $service.StartMode -eq 'Disabled')}
   'M01' {
    $tasks=@(Get-ScheduledTask -ErrorAction Stop | Where-Object {($_.TaskPath -eq '\SummitScenario\' -and $_.TaskName -eq 'PartnerCacheSync') -or ($_.Actions.Arguments -match 'SummitScenario\\partner-cache\.cmd')})
    $pass=(@($tasks | Where-Object State -ne Disabled).Count -eq 0 -and -not(Test-Path 'C:\ProgramData\SummitScenario\partner-cache.cmd'))
   }
   {$_ -in @('F01','F02')} {
    $root='C:\Users\Public\Documents\SummitPartner'
    if(-not(Test-Path $root)){throw 'Required partner document directory missing'}
    $hash=if($Id -eq 'F01'){$meta.prohibitedCredentialHash}else{$meta.prohibitedArchiveHash}
    $pass=$true
    foreach($file in Get-ChildItem $root -File -Recurse -Force){
     if((Get-FileHash $file.FullName -Algorithm SHA256).Hash -eq $hash){$pass=$false;break}
     if($Id -eq 'F01' -and $file.Length -lt 1048576 -and (Get-Content $file.FullName -Raw) -match 'FICTIONAL-TRAINING-CREDENTIALS'){$pass=$false;break}
    }
   }
   {$_ -in @('Q01','Q02','Q03')} {
    $number=[int]$Id.Substring(1)
    $path="C:\Users\Public\Documents\SummitCompetition\Forensic Question $number.txt"
    if(-not(Test-Path $path)){throw 'Answer file missing'}
    $answer=Get-AnswerValue (Get-Content $path -Raw)
    $pass=($null -ne $answer -and $answer -ne '' -and (Get-TextHash $answer) -eq $meta.answerHashes[$number-1])
   }
   default {throw 'Unknown check'}
  }
  return Get-ForumVerdict $pass
 } catch {return 'ERROR'}
}
if($All){foreach($id in @('U01','U02','I01','I02','P01','P02','P03','P04','P05','A01','I03','I04','W01','S01','M01','F01','F02','Q01','Q02','Q03')){[pscustomobject]@{id=$id;verdict=Invoke-ForumCheck $id}}}
elseif($Check){Invoke-ForumCheck $Check}
