# Final read-only verification runs as SYSTEM, matching CSSClient's actual identity.
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\SummitCompetitionExpansion-20261004'
$manifest=Get-Content "$root\manifest.json" -Raw | ConvertFrom-Json
try{
 if($env:COMPUTERNAME -ne 'DC01' -or $manifest.Checks -ne 28 -or $manifest.Vulnerabilities -ne 25){throw 'Identity/count mismatch'}
 $config=Get-Content "$root\scoring.conf" -Raw
 $sum=0;foreach($m in [regex]::Matches($config,'(?m)^points = (\d+)')){$sum+=[int]$m.Groups[1].Value}
 if($sum -ne 100 -or [regex]::Matches($config,'(?m)^\[\[check\]\]').Count -ne 28){throw 'Count/points mismatch'}
 if((Get-FileHash "$root\scoring.conf").Hash -ne $manifest.ConfigHash -or (Get-FileHash C:\aeacus\probes\Check-Competition.ps1).Hash -ne $manifest.BaseProbeHash -or (Get-FileHash C:\aeacus\probes\Check-Extra.ps1).Hash -ne $manifest.ExtraProbeHash){throw 'Deployed contract fingerprint mismatch'}
 $base=@('casey','drew','privilege','contractor','smb','dns-update','dns-transfer','spooler','registry','logging','persistence','credentials','media','fq1','fq2','fq3')
 $extra=@('share-encryption','share-permission','share-ntfs','automation-acl','uac-consent','uac-desktop','defender','firewall','audit-logon','audit-process','updates','root-trust')
 $results=@()
 foreach($id in ($base+$extra)){
  $script=if($id -in $extra){'C:\aeacus\probes\Check-Extra.ps1'}else{'C:\aeacus\probes\Check-Competition.ps1'}
  $out=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $script -Check $id
  if($LASTEXITCODE -ne 0 -or ($out -join "`n").Trim() -ne 'FAIL'){throw "Final runtime-context probe mismatch: $id"}
  $results+=[pscustomobject]@{ID=$id;Verdict='FAIL'}
 }
 foreach($i in 1..3){$file="C:\SummitCompetition\Forensic Question $i.txt";$body=Get-Content $file -Raw;$parts=[regex]::Split($body,'\r?\nAnswer:\s*\r?\n',2);if($parts.Count -ne 2 -or $parts[1].Trim()){throw 'Public answer not blank'};if(-not (Test-Path "C:\Users\Public\Desktop\Forensic Question $i.lnk")){throw 'Question shortcut missing'}}
 if(Test-Path C:\aeacus\scoring.conf){throw 'Runtime plaintext remains'}
 $service=Get-Service CSSClient
 if($service.Status -ne 'Running' -or $service.StartType -ne 'Automatic'){throw 'Scoring service unhealthy'}
 $report=Get-Item C:\aeacus\assets\ScoringReport.html
 $html=Get-Content $report.FullName -Raw
 if($html -notmatch '0 out of 100 points received' -or $html -notmatch '</html>' -or ((Get-Date)-$report.LastWriteTime).TotalSeconds -gt 180){throw 'Fresh complete 0/100 report absent'}
 [pscustomobject]@{Machine='DC01';Identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name;Vulnerabilities=25;Questions=3;Checks=28;Points=100;Score=0;NativeErrors=0;AllPlanted=$true;Results=$results;Service='Running';Startup='Automatic';EncryptedOnly=$true;PublicAnswersBlank=$true;QuestionShortcuts=3;ReportTime=$report.LastWriteTime.ToString('o');ManualAcceptance='PENDING';Time=(Get-Date).ToString('o')} | ConvertTo-Json -Depth 5 | Set-Content "$root\final-verification.json"
}catch{$_ | Out-String | Set-Content "$root\final-verification-failure.txt";exit 1}
