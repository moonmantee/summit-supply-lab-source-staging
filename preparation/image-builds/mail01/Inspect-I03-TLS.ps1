$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
$auth='C:\Program Files (x86)\Mail Enable\Config\AUTH.TAB'
$row=@([IO.File]::ReadAllLines($auth) | Where-Object {($_.Split([char]9)[0]) -ieq 'operations@Summit'})
if($row.Count -ne 1){throw 'Expected exactly one operations account'}
$fields=$row[0].Split([char]9)
$cert=Get-ChildItem Cert:\LocalMachine\My | Where-Object {$_.Thumbprint -eq '9022BCC5290165636CD08B5B636B592D16314674'}
[pscustomobject]@{
 authentication=[pscustomobject]@{login=$fields[0];columns=$fields.Count;passwordLength=$fields[2].Length;encryptedPasswordFormat=($fields[2] -match '^\[.*\]|^\$|^\!\!')}
 certificates=@($cert | Select-Object Subject,Thumbprint,NotAfter,@{n='names';e={$_.DnsNameList.Unicode -join ','}})
} | ConvertTo-Json -Depth 4
