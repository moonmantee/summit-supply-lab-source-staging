$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
. C:\aeacus\probes\Probe.ps1
$results=@(foreach($id in Get-ControlIds){[pscustomobject]@{id=$id;verdict=Invoke-MailCheck $id}})
if(@($results|Where-Object verdict -ne FAIL).Count){throw 'Final participant state must have 25 FAIL and zero ERROR'}
if(Test-Path C:\aeacus\scoring.conf){throw 'Runtime plaintext configuration leaked'}
$svc=Get-Service CSSClient;if($svc.Status -ne 'Running' -or $svc.StartType -ne 'Automatic'){throw 'Production scorer unhealthy'}
$file=Get-Item C:\aeacus\assets\ScoringReport.html;$html=Get-Content $file.FullName -Raw
if($html -notmatch '(?<!\d)0 out of 100 points received' -or $html -notmatch '0 out of 25' -or $html -notmatch '</html>'){throw 'Fresh complete starting report mismatch'}
if(([DateTime]::UtcNow - $file.LastWriteTimeUtc).TotalSeconds -gt 150){throw 'Report is stale'}
$services=@(Get-Service|Where-Object {$_.Name -like 'ME*' -or $_.Name -in @('W3SVC','sshd','WinDefend')}|Select-Object Name,Status)
if(@($services|Where-Object Status -ne Running).Count){throw 'Required service stopped'}
if(-not(Test-ComputerSecureChannel)){throw 'Domain secure channel lost'}
if(-not(Get-MpComputerStatus).RealTimeProtectionEnabled){throw 'Real-time Defender protection lost'}
$meta=Get-Content C:\aeacus\probes\metadata.json -Raw|ConvertFrom-Json
[ordered]@{machine='MAIL01';issues=25;points=100;startingScore=0;probeErrors=0;results=$results;services=$services;encryptedScorerStatus=[string]$svc.Status;encryptedScorerStartup=[string]$svc.StartType;reportUtc=$file.LastWriteTimeUtc.ToString('o');probeHash=(Get-FileHash C:\aeacus\probes\Probe.ps1).Hash;domainTrust=$true;defenderRealTime=$true;manualAcceptance='pending';export='not-performed';utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 6
