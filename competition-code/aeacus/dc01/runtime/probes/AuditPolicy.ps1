function Test-SummitAuditPolicy {
 param($State,$Baseline,[string]$Check)
 if($null -eq $State -or $null -eq $State.Accounts -or @($Baseline).Count -ne 20){return $false}
 foreach($expected in $Baseline){
  $actual=@($State.Accounts | Where-Object {$_.SID -eq $expected.SID -and $_.Account -eq $expected.Account})
  if($actual.Count -ne 1){return $false}
  if($expected.Role -ne 'departed' -and (-not $actual[0].Enabled -or $actual[0].LockedOut)){return $false}
 }
 switch($Check){
  'casey-disabled' {return -not ($State.Accounts | Where-Object Account -eq 'casey.turner').Enabled}
  'drew-disabled' {return -not ($State.Accounts | Where-Object Account -eq 'drew.parker').Enabled}
  'standard-unprivileged' {return @($State.Accounts | Where-Object {$_.Role -ne 'admin' -and $_.Privileged}).Count -eq 0}
  'admins-authorized' {return $null -ne $State.UnexpectedDomainAdmins -and $State.UnexpectedDomainAdmins -eq 0 -and @($State.Accounts | Where-Object {$_.Role -eq 'admin' -and -not $_.DomainAdmin}).Count -eq 0}
  default {return $false}
 }
}
