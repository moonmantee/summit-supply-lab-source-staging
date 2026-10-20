param([Parameter(Mandatory=$true)][string]$Check)
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
try {
 . "$PSScriptRoot\AuditPolicy.ps1"
 Import-Module ActiveDirectory
 $baseline=Get-Content "$PSScriptRoot\verified-roster.json" -Raw | ConvertFrom-Json
 $domain=Get-ADDomain
 if($domain.DNSRoot -ne 'corp.summit.test'){throw 'Wrong domain'}
 $privilegedSids=@("$($domain.DomainSID)-512","$($domain.DomainSID)-518","$($domain.DomainSID)-519",'S-1-5-32-544','S-1-5-32-548','S-1-5-32-549','S-1-5-32-550','S-1-5-32-551')
 $accounts=@()
 foreach($entry in $baseline){
  $identity=Get-ADUser -Identity $entry.SID
  $user=Get-ADUser -Filter * -SearchBase $identity.DistinguishedName -SearchScope Base -Properties Enabled,LockedOut,tokenGroups
  $groups=@($user.tokenGroups | ForEach-Object {$_.Value})
  $accounts += [pscustomobject]@{SID=$user.SID.Value;Account=$user.SamAccountName;Role=$entry.Role;Enabled=$user.Enabled;LockedOut=$user.LockedOut;Privileged=(@($groups | Where-Object {$_ -in $privilegedSids}).Count -gt 0);DomainAdmin=("$($domain.DomainSID)-512" -in $groups)}
 }
 $allowedAdmins=@("$($domain.DomainSID)-500") + @($baseline | Where-Object Role -eq 'admin' | ForEach-Object SID)
 $unexpected=@(Get-ADGroupMember -Identity "$($domain.DomainSID)-512" -Recursive | Where-Object {$_.SID.Value -notin $allowedAdmins}).Count
 $state=[pscustomobject]@{Accounts=$accounts;UnexpectedDomainAdmins=$unexpected}
 if(Test-SummitAuditPolicy -State $state -Baseline $baseline -Check $Check){'PASS'}else{'FAIL'}
} catch { [Console]::Error.WriteLine('Domain audit could not be evaluated: '+$_.Exception.Message); exit 1 }
