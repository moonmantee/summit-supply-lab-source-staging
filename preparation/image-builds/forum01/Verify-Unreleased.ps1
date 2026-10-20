$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'FORUM01'){throw 'Guest identity mismatch'}
. C:\aeacus\probes\Probe.ps1
$results=@(foreach($id in @('U01','U02','I01','I02','P01','P02','P03','P04','P05','A01','I03','I04','W01','S01','M01','F01','F02','Q01','Q02','Q03')){[pscustomobject]@{id=$id;verdict=Invoke-ForumCheck $id}})
if(@($results | Where-Object verdict -ne FAIL).Count){throw 'Challenge state contains probe errors or unstaged controls'}
$r=Invoke-WebRequest http://127.0.0.1/ -UseBasicParsing -TimeoutSec 20
if($r.StatusCode -ne 200 -or $r.Content -notmatch 'Summit Partner'){throw 'Forum unhealthy'}
foreach($name in @('W3SVC','FTPSVC','sshd')){if((Get-Service $name).Status -ne 'Running'){throw 'Required service stopped'}}
foreach($number in 1..3){$text=Get-Content "C:\Users\Public\Documents\SummitCompetition\Forensic Question $number.txt" -Raw;if((Get-AnswerValue $text) -ne ''){throw 'Public forensic answer not blank'}}
$defender=Get-MpComputerStatus
$scorer=Get-Service CSSClient -ErrorAction SilentlyContinue
[ordered]@{machine='FORUM01';challengeControls=20;expectedStartingScore=0;allChecks='FAIL';probeErrors=0;forensicAnswers='blank';forumHttpStatus=200;requiredServices='running';antivirusEnabled=$defender.AntivirusEnabled;realTimeProtectionEnabled=$defender.RealTimeProtectionEnabled;scorerService=if($scorer){[string]$scorer.Status}else{'removed by Defender'};automatedScoring='blocked';manualAcceptance='pending';vmExport='not performed';utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json
