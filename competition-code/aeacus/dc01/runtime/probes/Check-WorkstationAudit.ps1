param([Parameter(Mandatory=$true)][ValidateSet('admins','recovery','guest')][string]$Check)
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
try {
 $computer=Get-CimInstance Win32_ComputerSystem
 if($computer.Name -ne 'WORKSTATION01' -or -not $computer.PartOfDomain -or $computer.Domain -ne 'corp.summit.test'){throw 'Unexpected workstation identity'}
 $jonah=Get-LocalUser -SID 'S-1-5-21-1218218446-1336531816-251651155-1001'
 if(-not $jonah.Enabled){'FAIL'; exit 0}
 switch($Check){
  'admins' {
   $allowed=@('S-1-5-21-1538098495-642441483-3435665723-512','S-1-5-21-1218218446-1336531816-251651155-500','S-1-5-21-1218218446-1336531816-251651155-1001')
   $members=@(Get-LocalGroupMember -SID S-1-5-32-544 | ForEach-Object {$_.SID.Value})
   $pass=@($members | Where-Object {$_ -notin $allowed}).Count -eq 0 -and @($allowed | Where-Object {$_ -notin $members}).Count -eq 0
  }
  'recovery' {$pass=$jonah.Enabled -and $jonah.Name -eq 'jonah'}
  'guest' {$pass=-not (Get-LocalUser -SID 'S-1-5-21-1218218446-1336531816-251651155-501').Enabled}
 }
 if($pass){'PASS'}else{'FAIL'}
} catch {[Console]::Error.WriteLine('Workstation audit could not be evaluated: '+$_.Exception.Message);exit 1}
