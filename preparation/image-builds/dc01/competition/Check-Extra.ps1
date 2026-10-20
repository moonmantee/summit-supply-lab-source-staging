param([Parameter(Mandatory=$true)][string]$Check)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
try{
 Import-Module ActiveDirectory
 $m=Get-Content "$PSScriptRoot\extras.json" -Raw | ConvertFrom-Json
 if($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong guest'}
 foreach($name in @('NTDS','DNS','Netlogon','DFSR','W32Time','sshd')){if((Get-Service $name).Status -ne 'Running'){throw 'Required service unavailable'}}
 foreach($e in $m.Roster){$u=Get-ADUser $e.SID -Properties LockedOut;if($e.Role -ne 'departed' -and (-not $u.Enabled -or $u.LockedOut)){throw 'Employee unavailable'}}
 function NoEmployeeWrite([string]$Path){
  $identity=Get-ADUser emma.wilson
  $user=Get-ADUser -Filter * -SearchBase $identity.DistinguishedName -SearchScope Base -Properties tokenGroups
  $sids=@($user.SID.Value,'S-1-1-0','S-1-5-11','S-1-5-32-545')+@($user.tokenGroups | ForEach-Object {$_.Value})
  $write=[Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
  $allow=0;$remaining=[int]$write
  foreach($r in (Get-Acl -LiteralPath $Path).Access){
   if(($r.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0){continue}
   if($r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -in $sids){
    $bits=[int]$r.FileSystemRights -band $remaining
    if($r.AccessControlType -eq 'Allow'){$allow=$allow -bor $bits}
    $remaining=$remaining -band (-bnot $bits)
   }
  }
  ($allow -eq 0)
 }
 $pass=$false
 switch($Check){
  'share-encryption' {$pass=(Get-SmbShare SummitOps).EncryptData}
  'share-permission' {
   $rules=@(Get-SmbShareAccess SummitOps)
   $bad=@($rules | Where-Object {$_.AccessControlType -eq 'Allow' -and ($_.AccountName -notin @('CORP\Domain Users','BUILTIN\Administrators','CORP\Domain Admins','NT AUTHORITY\SYSTEM') -or ($_.AccountName -eq 'CORP\Domain Users' -and $_.AccessRight -ne 'Read'))})
   $pass=$bad.Count -eq 0 -and @($rules | Where-Object {$_.AccountName -eq 'CORP\Domain Users' -and $_.AccessControlType -eq 'Allow' -and $_.AccessRight -eq 'Read'}).Count -eq 1
  }
  'share-ntfs' {$pass=(NoEmployeeWrite 'C:\SummitSupply\Operations') -and (NoEmployeeWrite 'C:\SummitSupply\Operations\inventory.csv')}
  'automation-acl' {
   $task=Get-ScheduledTask SummitInventoryMaintenance
   if($task.State -eq 'Disabled'){throw 'Required maintenance task disabled'}
   $pass=(NoEmployeeWrite 'C:\SummitSupply\Automation') -and (NoEmployeeWrite 'C:\SummitSupply\Automation\inventory-maintenance.cmd')
  }
  'uac-consent' {$p=Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System;$pass=$p.EnableLUA -eq 1 -and $p.ConsentPromptBehaviorAdmin -in @(1,2,3,4,5)}
  'uac-desktop' {$p=Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System;$pass=$p.EnableLUA -eq 1 -and $p.PromptOnSecureDesktop -eq 1}
  'defender' {$s=Get-MpComputerStatus;$pass=$s.AntivirusEnabled -and $s.RealTimeProtectionEnabled -and -not (Get-MpPreference).DisableRealtimeMonitoring}
  'firewall' {$pass=@(Get-NetFirewallProfile -PolicyStore ActiveStore | Where-Object Enabled -ne 'True').Count -eq 0}
  {$_ -in @('audit-logon','audit-process')} {
   $guid=if($Check -eq 'audit-logon'){'{0CCE9215-69AE-11D9-BED3-505054503030}'}else{'{0CCE922B-69AE-11D9-BED3-505054503030}'}
   $csv=& auditpol.exe /get "/subcategory:$guid" /r
   if($LASTEXITCODE -ne 0){throw 'Audit query failed'}
   $row=($csv | Where-Object {$_ -and $_.Trim()} | ConvertFrom-Csv | Where-Object {$_.'Subcategory GUID' -eq $guid})
   if(-not $row){throw 'Audit row absent'}
   $pass=$row.'Inclusion Setting' -eq 'Success and Failure'
  }
  'updates' {$pass=(Get-Service wuauserv).StartType -ne 'Disabled'}
  'root-trust' {$pass=@(Get-ChildItem Cert:\LocalMachine\Root | Where-Object Thumbprint -eq $m.RootThumbprint).Count -eq 0}
  default {throw 'Unknown extra control'}
 }
 if($pass){'PASS'}else{'FAIL'}
}catch{[Console]::Error.WriteLine('ERROR: '+$_.Exception.Message);exit 1}
