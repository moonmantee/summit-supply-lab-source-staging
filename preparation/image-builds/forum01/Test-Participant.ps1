#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
. "$PSScriptRoot\Native.ps1"
. C:\aeacus\probes\Probe.ps1
$root='C:\ProgramData\SummitLab\ForumCompetition-20261004'
$secrets=Get-Content "$root\secrets.json" -Raw | ConvertFrom-Json
$meta=Get-Content "$root\metadata.json" -Raw | ConvertFrom-Json
$restoreAuditGrant=([ForumNative]::GroupSids('Administrators') -contains $meta.auditSid)
if($restoreAuditGrant){Remove-LocalGroupMember -Group Administrators -Member forum.audit}
if([ForumNative]::GroupSids('Administrators') -contains $meta.auditSid){throw 'Audit identity is not standard for participant-file tests'}
try {
$results=@()
foreach($identity in @(@{name='labadmin';password=$secrets.labadmin},@{name='forum.audit';password=$secrets.audit})) {
 foreach($number in 1..3) {
  $path="C:\Users\Public\Documents\SummitCompetition\Forensic Question $number.txt"
  $before=(Get-FileHash $path).Hash
  if(-not[ForumNative]::SaveUnchanged($identity.name,$env:COMPUTERNAME,$identity.password,$path)){throw 'Participant answer save failed'}
  if((Get-FileHash $path).Hash -ne $before){throw 'Question contents changed in unchanged-save test'}
  if((Invoke-ForumCheck ('Q0'+$number)) -ne 'FAIL'){throw 'Blank answers earned points'}
  $results+=[pscustomobject]@{identity=$identity.name;question=$number;readAndSave=$true;contentsPreserved=$true;blankAnswerVerdict='FAIL'}
 }
 if(-not[ForumNative]::CanOpen($identity.name,$env:COMPUTERNAME,$identity.password,'C:\Users\Public\Documents\SummitCompetition\README.html',[IO.FileAccess]::Read)){throw 'Participant README unreadable'}
 if(Test-Path C:\aeacus\assets\ScoringReport.html){if(-not[ForumNative]::CanOpen($identity.name,$env:COMPUTERNAME,$identity.password,'C:\aeacus\assets\ScoringReport.html',[IO.FileAccess]::Read)){throw 'Participant report unreadable'}}
}
$shell=New-Object -ComObject WScript.Shell
foreach($number in 1..3){
 $link=$shell.CreateShortcut("C:\Users\Public\Desktop\Forensic Question $number.lnk")
 if($link.TargetPath -ne "C:\Users\Public\Documents\SummitCompetition\Forensic Question $number.txt"){throw 'Forensic shortcut points to wrong file'}
}
# Negative controls: wrong answers, renamed forbidden copies, missing business config.
$answer='C:\Users\Public\Documents\SummitCompetition\Forensic Question 1.txt'
$saved=[IO.File]::ReadAllBytes($answer)
try{[IO.File]::AppendAllText($answer,"WRONG-ANSWER`r`n");if((Invoke-ForumCheck Q01) -ne 'FAIL'){throw 'Wrong answer awarded credit'}}finally{[IO.File]::WriteAllBytes($answer,$saved)}
$copy='C:\Users\Public\Documents\SummitPartner\renamed-forensic-control.bin'
try{Copy-Item "$root\fixtures\contractor-notes.txt" $copy;if((Invoke-ForumCheck F01) -ne 'FAIL'){throw 'Renamed prohibited content evades probe'}}finally{Remove-Item -LiteralPath $copy}
$results | ConvertTo-Json -Depth 3 | Set-Content "$root\participant-file-tests.json" -Encoding UTF8
$results | ConvertTo-Json -Depth 3
} finally {if($restoreAuditGrant){Add-LocalGroupMember -Group Administrators -Member forum.audit}}
