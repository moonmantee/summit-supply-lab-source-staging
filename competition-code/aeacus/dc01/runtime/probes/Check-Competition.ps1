param([Parameter(Mandatory=$true)][string]$Check,[string]$AnswerRoot='C:\SummitCompetition')
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
try {
 Import-Module ActiveDirectory
 $meta=Get-Content "$PSScriptRoot\targets.json" -Raw | ConvertFrom-Json
 if($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong guest'}
 # Every scored repair must preserve the named roster, directory and DNS services.
 foreach($entry in $meta.Roster){
  $u=Get-ADUser $entry.SID -Properties LockedOut
  if($u.SamAccountName -ne $entry.Account){throw 'Roster identity mismatch'}
  if($entry.Role -ne 'departed' -and (-not $u.Enabled -or $u.LockedOut)){throw 'Required account unavailable'}
 }
 foreach($name in @('NTDS','DNS','Netlogon','DFSR','W32Time','sshd')){if((Get-Service $name).Status -ne 'Running'){throw 'Required service unavailable'}}
 if((Resolve-DnsName dc01.corp.summit.test -Type A -Server 127.0.0.1).IPAddress -notcontains '10.77.40.10'){throw 'Required DNS record unavailable'}
 $pass=$false
 switch($Check){
  'casey' {$pass=-not (Get-ADUser $meta.Casey).Enabled}
  'drew' {$pass=-not (Get-ADUser $meta.Drew).Enabled}
  'privilege' {
   $bad=@("$((Get-ADDomain).DomainSID)-512","$((Get-ADDomain).DomainSID)-518","$((Get-ADDomain).DomainSID)-519",'S-1-5-32-544','S-1-5-32-548','S-1-5-32-549','S-1-5-32-550','S-1-5-32-551')
   $excess=0
   foreach($e in $meta.Roster | Where-Object Role -ne 'admin'){
    $identity=Get-ADUser $e.SID
    $u=Get-ADUser -Filter * -SearchBase $identity.DistinguishedName -SearchScope Base -Properties tokenGroups
    if(@($u.tokenGroups).Count -eq 0){throw 'Effective group query returned no groups'}
    foreach($g in $u.tokenGroups){if($g -is [Security.Principal.SecurityIdentifier]){$value=$g.Value}else{$value=(New-Object Security.Principal.SecurityIdentifier($g,0)).Value};if($value -in $bad){$excess++}}
   }
   $pass=$excess -eq 0
  }
  'contractor' {
   $u=$null
   try{$u=Get-ADUser -Identity $meta.ContractorSID -ErrorAction Stop}catch [Microsoft.ActiveDirectory.Management.ADIdentityNotFoundException]{}
   $pass=($null -eq $u -or -not $u.Enabled)
  }
  'smb' {$pass=(Get-SmbServerConfiguration).RequireSecuritySignature}
  'dns-update' {$pass=(Get-DnsServerZone -Name corp.summit.test).DynamicUpdate -eq 'Secure'}
  'dns-transfer' {$pass=(Get-DnsServerZone -Name corp.summit.test).SecureSecondaries -eq 'NoTransfer'}
  'spooler' {$s=Get-Service Spooler;$pass=$s.Status -eq 'Stopped' -and $s.StartType -eq 'Disabled'}
  'registry' {$s=Get-Service RemoteRegistry;$pass=$s.Status -eq 'Stopped' -and $s.StartType -eq 'Disabled'}
  'logging' {$log=Get-WinEvent -ListLog Security;$pass=$log.IsEnabled -and $log.MaximumSizeInBytes -ge 67108864}
  'persistence' {
   $tasks=@(Get-ScheduledTask | Where-Object {$_.TaskName -eq 'SummitLegacyTelemetry' -or (@($_.Actions | ForEach-Object Arguments) -join ' ') -match 'legacy-telemetry\.cmd'})
   $enabled=@($tasks | Where-Object State -ne 'Disabled')
   $pass=$enabled.Count -eq 0 -and -not (Test-Path 'C:\ProgramData\SummitCompetition\legacy-telemetry.cmd')
  }
  'credentials' {
   $matches=@(Get-ChildItem 'C:\SummitSupply' -File -Recurse | Where-Object {$_.Length -lt 1MB} | Where-Object {(Get-Content $_.FullName -Raw) -match 'SUMMIT-FICTIONAL-CREDENTIALS-20261004'})
   $pass=$matches.Count -eq 0
  }
  'media' {
   $matches=@(Get-ChildItem 'C:\SummitSupply' -File -Recurse | Where-Object {$_.Length -lt 1MB} | Where-Object {(Get-Content $_.FullName -Raw) -match 'SUMMIT-UNAUTHORIZED-MEDIA-20261004'})
   $pass=$matches.Count -eq 0
  }
  {$_ -in @('fq1','fq2','fq3')} {
   $index=[int]$Check.Substring(2)
   $file="$AnswerRoot\Forensic Question $index.txt"
   if(-not (Test-Path $file)){throw 'Answer file missing'}
   $body=Get-Content $file -Raw
   $m=[regex]::Match($body,'(?s)\r?\nAnswer:\s*\r?\n(.*)$')
   if(-not $m.Success){throw 'Answer section missing'}
   $answer=$m.Groups[1].Value.Trim().ToLowerInvariant()
   $digest=[Security.Cryptography.SHA256]::Create()
   try{$hash=([BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($answer)))).Replace('-','').ToLowerInvariant()}finally{$digest.Dispose()}
   $pass=$hash -eq $meta.AnswerHashes.($Check)
  }
  default {throw 'Unknown control'}
 }
 if($pass){'PASS'}else{'FAIL'}
}catch{[Console]::Error.WriteLine('ERROR: '+$_.Exception.Message);exit 1}
