$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
Import-Module WebAdministration
$o=[ordered]@{machine=$env:COMPUTERNAME;os=(Get-CimInstance Win32_OperatingSystem).Caption;domain=(Get-CimInstance Win32_ComputerSystem).Domain;secureChannel=Test-ComputerSecureChannel;services=@(Get-Service|Where-Object {$_.Name -like 'ME*' -or $_.Name -in @('sshd','W3SVC','WinDefend','CSSClient')}|Select-Object Name,Status,StartType);scorerHashes=@(Get-FileHash C:\aeacus\aeacus.exe,C:\aeacus\phocus.exe|Select-Object Path,Hash);mailConfigFiles=@(Get-ChildItem 'C:\Program Files (x86)\Mail Enable\Config' -File -Filter *.TAB|Select-Object Name,Length);mpExclusions=(Get-MpPreference).ExclusionPath;scorerVersion=(& C:\aeacus\aeacus.exe version|Out-String).Trim();siteBindings=@(Get-Website|Select-Object Name,State,@{n='Bindings';e={$_.Bindings.Collection.bindingInformation -join ';'}})}
$binding=@(Get-WebBinding -Name 'MailEnable WebMail' -Protocol https);$o.certificateThumbprint=[string]$binding[0].certificateHash
$o.webmailStatus='pending pinned-leaf preservation test; Windows native trust failed'
$o | ConvertTo-Json -Depth 6
