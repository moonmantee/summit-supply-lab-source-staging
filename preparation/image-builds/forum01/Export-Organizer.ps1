#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\SummitLab\ForumCompetition-20261004'
$source='C:\ProgramData\SummitLab\ForumCompetitionSource-20261004'
$status=Get-Content "$root\status.json" -Raw | ConvertFrom-Json
if($status.phase -notin @('runtime-verified','runtime-blocked-defender')){throw 'Organizer export requires completed guest rehearsals and a recorded deployment outcome'}
$secrets=Get-Content "$root\secrets.json" -Raw | ConvertFrom-Json
$credentials=@(
 'Organizer-only: newly generated forum01 exercise credentials. Do not publish.',
 ('FORUM01\labadmin (local competitor administrator / recovery): '+$secrets.labadmin),
 ('FORUM01\forum.audit (authorized standard audit identity): '+$secrets.audit),
 'Existing organizer, FTP and domain passwords were not retrieved or changed.'
)
$credentials | Set-Content "$root\INITIAL-CREDENTIALS.txt" -Encoding UTF8
$sources="$root\build-source"
if(Test-Path $sources){throw 'Previous source export exists; do not replace it'}
New-Item -ItemType Directory $sources | Out-Null
Copy-Item "$source\*" $sources -Recurse
if(Test-Path C:\aeacus\assets\ScoringReport.html){Copy-Item C:\aeacus\assets\ScoringReport.html "$root\last-production-report.html"}
$archive="$root\organizer-records.zip"
if(Test-Path $archive){throw 'Previous organizer archive exists; do not replace it'}
Compress-Archive -Path "$root\backup","$root\fixtures",$sources,"$root\*.json","$root\matrix.jsonl","$root\INITIAL-CREDENTIALS.txt","$root\last-production-report.html" -DestinationPath $archive
$hash=(Get-FileHash $archive -Algorithm SHA256).Hash
[ordered]@{archive=$archive;hash=$hash;phase=$status.phase;generatedExerciseCredentialsOnly=$true} | ConvertTo-Json
