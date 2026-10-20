$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
$config='C:\Program Files (x86)\Mail Enable\Config'
$postoffices=@(Get-ChildItem -LiteralPath (Join-Path $config 'Postoffices') -Directory | Select-Object -ExpandProperty Name)
$mailboxes=@()
foreach($postoffice in $postoffices){
 $file=Join-Path (Join-Path (Join-Path $config 'Postoffices') $postoffice) 'MAILBOX.TAB'
 if(Test-Path -LiteralPath $file){
  foreach($line in [IO.File]::ReadAllLines($file)){
   $fields=$line.Split([char]9)
   if($fields[0]){$mailboxes += [pscustomobject]@{postoffice=$postoffice;name=$fields[0]}}
  }
 }
}
$domains=@()
$domainFile=Join-Path $config 'DOMAIN.TAB'
if(Test-Path -LiteralPath $domainFile){foreach($line in [IO.File]::ReadAllLines($domainFile)){$fields=$line.Split([char]9);if($fields.Count -ge 2){$domains += [pscustomobject]@{domain=$fields[0];postoffice=$fields[1]}}}}
Import-Module WebAdministration
$binding=@(Get-WebBinding -Name 'MailEnable WebMail' -Protocol https)
[pscustomobject]@{
 machine=$env:COMPUTERNAME
 services=@(Get-Service | Where-Object {$_.Name -like 'ME*' -or $_.Name -eq 'sshd'} | Select-Object Name,Status)
 listening=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in @(25,587,143,993,443)} | Select-Object LocalAddress,LocalPort)
 postoffices=$postoffices
 domains=$domains
 mailboxes=$mailboxes
 webCertificateThumbprint=[string]$binding[0].certificateHash
} | ConvertTo-Json -Depth 5
