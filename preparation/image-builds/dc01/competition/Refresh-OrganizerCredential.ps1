#Requires -RunAsAdministrator
# Refresh an existing organizer test credential; never change the AD password.
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'DC01'){throw 'Run only on DC01'}
Add-Type -AssemblyName System.DirectoryServices.AccountManagement
$path='C:\ProgramData\SummitLab\Private\initial-domain-credentials.json'
$records=Get-Content $path -Raw | ConvertFrom-Json
$entry=@($records | Where-Object Sam -eq 'alex.admin')
if($entry.Count -ne 1){throw 'Credential record mismatch'}
$secret=Read-Host 'Enter the CURRENT CORP\alex.admin password (no account password change)' -AsSecureString
$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
$context=New-Object System.DirectoryServices.AccountManagement.PrincipalContext([System.DirectoryServices.AccountManagement.ContextType]::Domain,'dc01.corp.summit.test')
try{
 $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
 if(-not $context.ValidateCredentials('alex.admin',$plain,[System.DirectoryServices.AccountManagement.ContextOptions]::Negotiate)){throw 'Current password did not authenticate; record unchanged'}
 $backup=$path+'.before-refresh-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
 Copy-Item -LiteralPath $path -Destination $backup
 $entry[0].Password=$plain
 $records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding UTF8
 'Organizer test record refreshed and authentication verified. No account password changed.'
}finally{$plain=$null;$context.Dispose();[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
