#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
$root='C:\ProgramData\SummitLab\MailForensics-20261004-v2';$public='C:\Users\Public\Documents\SummitMailCompetition';$scenario='C:\ProgramData\SummitMailScenario'
Import-Module WebAdministration
. "$PSScriptRoot\Native.ps1";. "$PSScriptRoot\MailWeb.ps1";. "$PSScriptRoot\Answer.ps1"
$site='IIS:\Sites\MailEnable WebMail';$reg='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System';$run='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run';$lsa='HKLM:\SYSTEM\CurrentControlSet\Control\Lsa';$update='HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU';$ssh='C:\ProgramData\ssh\sshd_config';$sshd='C:\Windows\System32\OpenSSH\sshd.exe'
$meta=Get-Content C:\aeacus\probes\metadata.json -Raw|ConvertFrom-Json
$secrets=Get-Content "$root\secrets.json" -Raw|ConvertFrom-Json
$original=Get-Content "$root\original.json" -Raw|ConvertFrom-Json
# Import only the exact previously-reviewed control setters from the verified source archive.
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile("$root\Build-Competition.ps1",[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Trusted setter source no longer parses'}
foreach($name in @('Reg-Set','Ssh-Set','Acl-Set','Set-Control','Assert-Business')){
 $definition=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object Name -eq $name)
 if($definition.Count -ne 1){throw 'Ambiguous trusted control setter'};. ([scriptblock]::Create($definition[0].Extent.Text))
}
. C:\aeacus\probes\Probe.ps1
function Json($v,$p){$v|ConvertTo-Json -Depth 14|Set-Content -LiteralPath $p -Encoding UTF8}
function Assert-Fq($id,$expected,$state,$answerRoot){$v=Invoke-ForensicCheck $id $answerRoot;if($v -ne $expected){throw "Forensic $id $state expected $expected got $v"};[ordered]@{id=$id;state=$state;verdict=$v;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Compress|Add-Content "$root\forensic-rehearsals.jsonl"}
function Restore-Start{foreach($id in Get-ControlIds){Set-Control $id $false};foreach($n in 1..3){if(Test-Path "$root\templates\question-$n.txt"){Copy-Item "$root\templates\question-$n.txt" "$public\Forensic Question $n.txt" -Force}}}
function Score($name,$config,$expected){
 Copy-Item $config C:\aeacus\scoring.conf -Force
 Push-Location C:\aeacus
 try{& .\aeacus.exe check|Out-Null;if($LASTEXITCODE){throw 'Engine check failed'};& .\aeacus.exe score|Out-Null;if($LASTEXITCODE){throw 'Engine score failed'};$h=Get-Content .\assets\ScoringReport.html -Raw;if($h -notmatch "(?<!\d)$expected out of 100 points received" -or $h -notmatch '</html>'){throw "Engine score mismatch $name"};Copy-Item .\assets\ScoringReport.html "$root\$name.html" -Force}finally{Pop-Location}
}
if(Test-Path "$root\phase.json"){throw 'Existing forensic transaction: diagnose or recover, never overwrite'}
foreach($p in @("$public\Forensic Evidence",'C:\aeacus\probes\Forensic.ps1','C:\aeacus\probes\Answer.ps1','C:\aeacus\probes\forensics.json')){if(Test-Path $p){throw 'Existing forensic resource conflict'}}
foreach($n in 1..3){foreach($p in @("$public\Forensic Question $n.txt","C:\Users\Public\Desktop\MAIL01 Forensic Question $n.lnk")){if(Test-Path $p){throw 'Existing question conflict'}}}
if($meta.issueCount -ne 25 -or $meta.points -ne 100){throw 'Base image contract changed'}
foreach($id in Get-ControlIds){if((Invoke-MailCheck $id) -ne 'FAIL'){throw 'Base challenge is not the verified starting state'}}
New-Item -ItemType Directory "$root\backup","$root\fixtures","$root\templates","$root\answers"|Out-Null
Copy-Item C:\aeacus\scoring.dat,C:\aeacus\probes\metadata.json,"$public\README.html" "$root\backup"
Copy-Item C:\aeacus\assets\ScoringReport.html "$root\backup\ScoringReport.html"
Copy-Item "$root\fictional-credentials.txt","$root\personal-media.zip" "$root\fixtures"
Assert-Business|Out-Null
Json @{phase='backup-ready';utc=[DateTime]::UtcNow.ToString('o')} "$root\phase.json"
Stop-Service CSSClient
try{
 New-Item -ItemType Directory "$public\Forensic Evidence"|Out-Null
 @('Synthetic training incident record; preserved independently of live cleanup targets.','2026-10-04T16:10:00-06:00 actor=MAIL01\mail.audit operation=change-permissions target=C:\ProgramData\SummitMailScenario\operations.ps1','2026-10-04T16:12:00-06:00 actor=MAIL01\mail.audit operation=register-task task=\SummitMailScenario\MailboxCacheSync payload=C:\ProgramData\SummitMailScenario\cache-marker.cmd')|Set-Content "$public\Forensic Evidence\incident-audit.txt" -Encoding UTF8
 Export-ScheduledTask -TaskPath '\SummitMailScenario\' -TaskName MailboxCacheSync|Set-Content "$public\Forensic Evidence\retained-task.xml" -Encoding UTF8
 Copy-Item "$scenario\cache-marker.cmd" "$public\Forensic Evidence\retained-payload.txt"
 & icacls.exe "$public\Forensic Evidence" /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-11:(OI)(CI)RX'|Out-Null;if($LASTEXITCODE){throw 'Evidence ACL failed'}
 $answers=@('mail01\mail.audit','\summitmailscenario\mailboxcachesync',(Get-FileHash "$public\Forensic Evidence\retained-payload.txt").Hash.ToLowerInvariant())
 $questions=@('Which account changed the maintenance-script permissions in the preserved incident record?','What is the full scheduled-task path used for the unauthorized activation shown in the retained evidence?','What is the SHA-256 hash of the retained payload file?')
 $formats=@('MACHINE\username; case insensitive','Full task path beginning with a backslash; case insensitive','64 hexadecimal characters; case insensitive')
 $evidence=@('incident-audit.txt','retained-task.xml','retained-payload.txt')
 $records=@();$shell=New-Object -ComObject WScript.Shell
 foreach($n in 1..3){
  $text="Forensic Question $n`r`n`r`nQuestion: $($questions[$n-1])`r`nEvidence: $public\Forensic Evidence\$($evidence[$n-1])`r`nAnswer format: $($formats[$n-1])`r`n`r`nAnswer:`r`n"
  [IO.File]::WriteAllText("$root\templates\question-$n.txt",$text,[Text.Encoding]::UTF8)
  Copy-Item "$root\templates\question-$n.txt" "$public\Forensic Question $n.txt"
  & icacls.exe "$public\Forensic Question $n.txt" /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' '*S-1-5-11:M'|Out-Null;if($LASTEXITCODE){throw 'Answer ACL failed'}
  Copy-Item "$root\templates\question-$n.txt" "$root\answers\Forensic Question $n.txt"
  $p="$public\Forensic Evidence\$($evidence[$n-1])"
  $records+=@{id=('Q0'+$n);category='Forensics Questions';points=4;target='MAIL01';answerHash=(Get-TextHash $answers[$n-1]);evidence=@(@{path=$p;sha256=(Get-FileHash $p).Hash});question=$questions[$n-1];status='prepared';probe="Forensic.ps1 -Check Q0$n";repair="Save the correct answer in Forensic Question $n.txt";dependencies='Retained evidence and scorer';preservation='Existing mail service/data, domain trust and access';recovery='Restore the blank question template'}
  $lnk=$shell.CreateShortcut("C:\Users\Public\Desktop\MAIL01 Forensic Question $n.lnk");$lnk.TargetPath='C:\Windows\System32\notepad.exe';$lnk.Arguments='"'+"$public\Forensic Question $n.txt"+'"';$lnk.Save()
 }
 Copy-Item "$root\Forensic.ps1","$root\Answer.ps1" C:\aeacus\probes
 Json @{questions=$records} C:\aeacus\probes\forensics.json
 . C:\aeacus\probes\Forensic.ps1
 Set-Control U02 $true
 try{foreach($user in @(@{n='mail.fallback';p=$secrets.fallback},@{n='mail.audit';p=$secrets.audit})){foreach($n in 1..3){$path="$public\Forensic Question $n.txt";if(-not[ForumNative]::CanOpen($user.n,'MAIL01',$user.p,$path,[IO.FileAccess]::Read) -or -not[ForumNative]::SaveUnchanged($user.n,'MAIL01',$user.p,$path)){throw 'Competitor cannot read/save answer'};[ordered]@{user=$user.n;question=$n;readSave=$true}|ConvertTo-Json -Compress|Add-Content "$root\participant-file-tests.jsonl"}}}finally{Set-Control U02 $false}
 foreach($n in 1..3){
  $id='Q0'+$n;Assert-Fq $id FAIL blank $public
  $template=[IO.File]::ReadAllText("$root\templates\question-$n.txt")
  [IO.File]::WriteAllText("$root\answers\Forensic Question $n.txt",$template+'wrong',[Text.Encoding]::UTF8);Assert-Fq $id FAIL wrong "$root\answers"
  [IO.File]::WriteAllText("$root\answers\Forensic Question $n.txt",$template+$answers[$n-1].ToUpperInvariant(),[Text.Encoding]::UTF8);Assert-Fq $id PASS correct "$root\answers"
  Assert-Fq $id FAIL final-blank $public
 }
 $base=[IO.File]::ReadAllText("$root\scoring.conf")
 $config=$base.Replace('Summit Supply - Mail Server','Summit Supply - Mail Server and Forensics')
 # Twelve existing controls become three points; thirteen remain four: 88 + 12 forensic points.
 $pointPattern=[regex]'(?m)^points = 4\r?$'
 if($pointPattern.Matches($config).Count -ne 25){throw 'Unexpected base points contract'}
 $config=$pointPattern.Replace($config,'points = 3',12)
 $reweighted=@(Get-ControlIds|Select-Object -First 12)
 foreach($q in $meta.issueManifest){if($q.id -in $reweighted){$q.points=3}}
 foreach($n in 1..3){$config+="`r`n[[check]]`r`nmessage = `"Forensic Question $n answered correctly`"`r`npoints = 4`r`n[[check.pass]]`r`ntype = 'CommandOutput'`r`ncmd = '& powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\aeacus\probes\Forensic.ps1 -Check Q0$n'`r`nvalue = 'PASS'`r`n"}
 [IO.File]::WriteAllText("$root\scoring-28.conf",$config,(New-Object Text.UTF8Encoding $false))
 $privateConfig=$config.Replace('Forensic.ps1 -Check Q01','Forensic.ps1 -AnswerRoot '+"$root\answers"+' -Check Q01').Replace('Forensic.ps1 -Check Q02','Forensic.ps1 -AnswerRoot '+"$root\answers"+' -Check Q02').Replace('Forensic.ps1 -Check Q03','Forensic.ps1 -AnswerRoot '+"$root\answers"+' -Check Q03')
 [IO.File]::WriteAllText("$root\solution.conf",$privateConfig,(New-Object Text.UTF8Encoding $false))
 Score starting "$root\scoring-28.conf" 0
 try{foreach($id in Get-ControlIds){Set-Control $id $true};Assert-Business|Out-Null;Score solution "$root\solution.conf" 100}finally{Restore-Start}
 Score restored "$root\scoring-28.conf" 0
 $readme=[IO.File]::ReadAllText("$public\README.html").Replace('25 security objectives, 100 points.','25 security controls (88 points) plus 3 forensic questions (12 points), 100 points.').Replace('No forensic objectives in this round.','Three separately scored forensic questions are included. Use their individual Public Desktop shortcuts; write only beneath Answer: and save. Answers are case insensitive and surrounding whitespace is ignored. Preserved evidence remains in Forensic Evidence even after live vulnerabilities are repaired.')
 [IO.File]::WriteAllText("$public\README.html",$readme,[Text.Encoding]::UTF8)
 foreach($q in $records){$q.status='runtime-verified';$q.evidenceRehearsals=@(Get-Content "$root\forensic-rehearsals.jsonl"|ForEach-Object {$_|ConvertFrom-Json}|Where-Object id -eq $q.id)}
 Json @{questions=$records} C:\aeacus\probes\forensics.json
 $meta.issueCount=28;$meta.points=100;$meta.expectedSolution=100;$meta.issueManifest+=@($records);$meta|Add-Member -NotePropertyName forensicCount -NotePropertyValue 3 -Force
 Json $meta C:\aeacus\probes\metadata.json
 Push-Location C:\aeacus
 try{& .\aeacus.exe encrypt|Out-Null;if($LASTEXITCODE){throw 'Encryption failed'};Remove-Item -LiteralPath .\scoring.conf;Remove-Item -LiteralPath .\assets\ScoringReport.html;$started=[DateTime]::UtcNow;Start-Service CSSClient
  $deadline=(Get-Date).AddMinutes(4)
  do{Start-Sleep -Seconds 2;$fresh=$false;if((Get-Service CSSClient).Status -ne 'Running'){throw 'Runtime stopped'};if(Test-Path .\assets\ScoringReport.html){$f=Get-Item .\assets\ScoringReport.html;$h=Get-Content $f.FullName -Raw;$fresh=($f.LastWriteTimeUtc -ge $started -and $h -match '(?<!\d)0 out of 100 points received' -and $h -match '0 out of 28' -and $h -match '</html>')}}until($fresh -or (Get-Date) -gt $deadline)
  if(-not$fresh){throw 'Fresh encrypted 28-objective report missing'}
 }finally{Pop-Location}
 foreach($id in Get-ControlIds){if((Invoke-MailCheck $id) -ne 'FAIL'){throw 'Existing vulnerability changed'}}
 foreach($n in 1..3){Assert-Fq ('Q0'+$n) FAIL production-blank $public}
 Json @{phase='runtime-verified';machine='MAIL01';securityControls=25;forensicQuestions=3;issues=28;points=100;starting=0;solution=100;restored=0;reportUtc=$f.LastWriteTimeUtc.ToString('o');forensicProbeHash=(Get-FileHash C:\aeacus\probes\Forensic.ps1).Hash;configHash=(Get-FileHash "$root\scoring-28.conf").Hash;preservation=Assert-Business;manualGui='pending'} "$root\phase.json"
 Get-Content "$root\phase.json"
}catch{
 $_|Out-String|Set-Content "$root\failure.txt"
 try{
  if((Get-Service CSSClient).Status -ne 'Stopped'){Stop-Service CSSClient}
  Restore-Start
  Copy-Item "$root\backup\scoring.dat" C:\aeacus\scoring.dat -Force;Copy-Item "$root\backup\metadata.json" C:\aeacus\probes\metadata.json -Force;Copy-Item "$root\backup\README.html" "$public\README.html" -Force
  foreach($n in 1..3){foreach($p in @("$public\Forensic Question $n.txt","C:\Users\Public\Desktop\MAIL01 Forensic Question $n.lnk")){if(Test-Path $p){Remove-Item -LiteralPath $p}}}
  foreach($p in @('C:\aeacus\scoring.conf','C:\aeacus\probes\Forensic.ps1','C:\aeacus\probes\Answer.ps1','C:\aeacus\probes\forensics.json')){if(Test-Path $p){Remove-Item -LiteralPath $p}}
  if(Test-Path "$public\Forensic Evidence"){$target=Get-Item -LiteralPath "$public\Forensic Evidence";if($target.FullName -ne 'C:\Users\Public\Documents\SummitMailCompetition\Forensic Evidence' -or ($target.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Unsafe recovery path'};Remove-Item -LiteralPath $target.FullName -Recurse -Force}
  Remove-Item C:\aeacus\assets\ScoringReport.html -ErrorAction SilentlyContinue
  $recoveryStarted=[DateTime]::UtcNow;Start-Service CSSClient;$deadline=(Get-Date).AddMinutes(4)
  do{Start-Sleep -Seconds 2;$ok=$false;if(Test-Path C:\aeacus\assets\ScoringReport.html){$rf=Get-Item C:\aeacus\assets\ScoringReport.html;$rh=Get-Content $rf.FullName -Raw;$ok=($rf.LastWriteTimeUtc -ge $recoveryStarted -and $rh -match '(?<!\d)0 out of 100 points received' -and $rh -match '(?<!\d)0 out of 25' -and $rh -match '</html>')}}until($ok -or (Get-Date) -gt $deadline)
  if(-not$ok){throw 'Fresh original recovery report missing'}
  foreach($id in Get-ControlIds){if((Invoke-MailCheck $id) -ne 'FAIL'){throw 'Original state recovery failed'}}
  Assert-Business|Out-Null
  Json @{phase='rollback-verified';utc=[DateTime]::UtcNow.ToString('o')} "$root\phase.json"
 }catch{$_|Out-String|Set-Content "$root\rollback-failure.txt";Json @{phase='recovery-needed'} "$root\phase.json"}
 throw
}
