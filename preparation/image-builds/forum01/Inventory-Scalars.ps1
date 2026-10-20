$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Import-Module WebAdministration
$os=Get-CimInstance Win32_OperatingSystem
$computer=Get-CimInstance Win32_ComputerSystem
$r=Invoke-WebRequest http://127.0.0.1/ -UseBasicParsing -TimeoutSec 15
$result=[ordered]@{
 computer=[string]$computer.Name;domain=[string]$computer.Domain;domainMember=[bool]$computer.PartOfDomain
 os=[string]$os.Caption;version=[string]$os.Version;architecture=[string]$os.OSArchitecture
 forumStatus=[int]$r.StatusCode;forumTitle=[string]([regex]::Match($r.Content,'<title>(.*?)</title>')).Groups[1].Value
 phpIni=([string](& C:\PHP\php.exe --ini | Out-String))
 phpEffective=([string](& C:\PHP\php.exe -i | Select-String '^(expose_php|display_errors|log_errors|allow_url_include|session.cookie_httponly) =>' | Out-String))
 configAcl=[string](Get-Acl C:\inetpub\wwwroot\config.php).Sddl
 webRootAcl=[string](Get-Acl C:\inetpub\wwwroot).Sddl
 phpIniAcl=[string](Get-Acl C:\PHP\php.ini).Sddl
 ftpFileHash=[string](Get-FileHash C:\FTP\Baseline\partner-info.txt -Algorithm SHA256).Hash
 forumConfigHash=[string](Get-FileHash C:\inetpub\wwwroot\config.php -Algorithm SHA256).Hash
 aeacusHash=[string](Get-FileHash C:\aeacus\aeacus.exe -Algorithm SHA256).Hash
 phocusHash=[string](Get-FileHash C:\aeacus\phocus.exe -Algorithm SHA256).Hash
}
$result | ConvertTo-Json -Depth 2
