$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
. C:\aeacus\probes\Probe.ps1
. C:\aeacus\probes\Forensic.ps1
$results=@(foreach($id in Get-ControlIds){[pscustomobject]@{id=$id;verdict=Invoke-MailCheck $id}})
if(@($results|Where-Object verdict -ne FAIL).Count){throw 'Final participant state must have 25 FAIL and zero ERROR'}
$results+=@(foreach($id in @('Q01','Q02','Q03')){[pscustomobject]@{id=$id;verdict=Invoke-ForensicCheck $id}})
if(@($results|Where-Object verdict -ne FAIL).Count){throw 'Forensic starting state invalid'}
if(Test-Path C:\aeacus\scoring.conf){throw 'Runtime plaintext configuration leaked'}
$svc=Get-Service CSSClient;if($svc.Status -ne 'Running' -or $svc.StartType -ne 'Automatic'){throw 'Production scorer unhealthy'}
$file=Get-Item C:\aeacus\assets\ScoringReport.html;$html=Get-Content $file.FullName -Raw
if($html -notmatch '(?<!\d)0 out of 100 points received' -or $html -notmatch '0 out of 28' -or $html -notmatch '</html>'){throw 'Fresh complete starting report mismatch'}
if(([DateTime]::UtcNow - $file.LastWriteTimeUtc).TotalSeconds -gt 150){throw 'Report is stale'}
$services=@(Get-Service|Where-Object {$_.Name -like 'ME*' -or $_.Name -in @('W3SVC','sshd','WinDefend')}|Select-Object Name,Status)
if(@($services|Where-Object Status -ne Running).Count){throw 'Required service stopped'}
if(-not(Test-ComputerSecureChannel)){throw 'Domain secure channel lost'}
if(-not(Get-MpComputerStatus).RealTimeProtectionEnabled){throw 'Real-time Defender protection lost'}
$meta=Get-Content C:\aeacus\probes\metadata.json -Raw|ConvertFrom-Json
[ordered]@{machine='MAIL01';issues=28;securityControls=25;forensicQuestions=3;points=100;startingScore=0;probeErrors=0;results=$results;services=$services;encryptedScorerStatus=[string]$svc.Status;encryptedScorerStartup=[string]$svc.StartType;reportUtc=$file.LastWriteTimeUtc.ToString('o');probeHash=(Get-FileHash C:\aeacus\probes\Probe.ps1).Hash;domainTrust=$true;defenderRealTime=$true;manualAcceptance='pending';export='not-performed';utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 6
