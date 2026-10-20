$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'FORUM01'){throw 'Guest identity mismatch'}
$service=Get-Service CSSClient
if($service.Status -ne 'Running' -or $service.StartType -ne 'Automatic'){throw 'Scorer is not running automatically'}
if(Test-Path C:\aeacus\scoring.conf){throw 'Runtime plaintext configuration remains'}
if(-not(Test-Path C:\aeacus\scoring.dat)){throw 'Encrypted runtime missing'}
$file=Get-Item C:\aeacus\assets\ScoringReport.html
$html=Get-Content $file.FullName -Raw
if($html -notmatch '0 out of 100 points received' -or $html -notmatch '</html>'){throw 'Final score report wrong or incomplete'}
if(([DateTime]::UtcNow-$file.LastWriteTimeUtc).TotalMinutes -gt 3){throw 'Production report stale'}
. C:\aeacus\probes\Probe.ps1
$ids=@('U01','U02','I01','I02','P01','P02','P03','P04','P05','A01','I03','I04','W01','S01','M01','F01','F02','Q01','Q02','Q03')
$verdicts=@(foreach($id in $ids){[pscustomobject]@{id=$id;verdict=Invoke-ForumCheck $id}})
if(@($verdicts | Where-Object verdict -ne FAIL).Count){throw 'Final challenge contains probe errors or unplanted controls'}
$r=Invoke-WebRequest http://127.0.0.1/ -UseBasicParsing -TimeoutSec 20
if($r.StatusCode -ne 200 -or $r.Content -notmatch 'Summit Partner'){throw 'Final forum unhealthy'}
foreach($name in @('W3SVC','FTPSVC','sshd')){if((Get-Service $name).Status -ne 'Running'){throw 'Final required service stopped'}}
foreach($number in 1..3){$text=Get-Content "C:\Users\Public\Documents\SummitCompetition\Forensic Question $number.txt" -Raw;if((Get-AnswerValue $text) -ne ''){throw 'A public forensic answer is not blank'}}
[ordered]@{machine='FORUM01';score=0;possible=100;issues=20;allPlantedChecks='FAIL';probeErrors=0;service='Running';startup='Automatic';runtimePlaintextAbsent=$true;publicAnswersBlank=$true;forumHttpStatus=200;requiredServices='running';reportUtc=$file.LastWriteTimeUtc.ToString('o');utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 3
