$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
$root=(Get-Content C:\ProgramData\SummitLab\MailCompetition-current.txt -Raw).Trim()
if($root -notmatch '^C:\\ProgramData\\SummitLab\\MailCompetition-[a-f0-9]{32}$'){throw 'Invalid record root'}
$status=Get-Content "$root\status.json" -Raw|ConvertFrom-Json
if($status.phase -ne 'runtime-verified'){throw 'Do not finalize an incomplete build'}
$secrets=Get-Content "$root\secrets.json" -Raw|ConvertFrom-Json
@('MAIL01 synthetic competition credentials (organizer only)',"mail.fallback : $($secrets.fallback)","mail.audit : $($secrets.audit)",'Existing administrator, domain and MailEnable passwords were not changed.')|Set-Content "$root\INITIAL-CREDENTIALS.txt"
$export='C:\ProgramData\SummitLab\MailOrganizerExport-'+[guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $export|Out-Null
& icacls.exe $export /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F'|Out-Null;if($LASTEXITCODE){throw 'Private export ACL failed'}
$sources=@($root,'C:\ProgramData\SummitLab\MailBuild-20261004','C:\ProgramData\SummitLab\MailCompetition-d1804031f863415093e5ef70fb1b3b4f','C:\ProgramData\SummitLab\MailCompetition-e6fa7807bc714eaab3ba8ebd964714d3','C:\ProgramData\SummitLab\MailRuntimePreflight-3cf54f3b7dda4ccbb0ddd686ccbfbd33')
$sources+=@(Get-ChildItem C:\ProgramData\SummitLab -Directory -Filter MailScorerRecovery-*|Where-Object {$_.Name -match '^MailScorerRecovery-[a-f0-9]{32}$'}|ForEach-Object {$_.FullName})
foreach($p in $sources){if(-not(Test-Path -LiteralPath $p)){throw 'Required organizer record missing'}}
Compress-Archive -LiteralPath $sources -DestinationPath "$export\organizer-records.zip"
$receipt=[ordered]@{machine='MAIL01';exportRoot=$export;archive="$export\organizer-records.zip";sha256=(Get-FileHash "$export\organizer-records.zip").Hash;sourceRoots=$sources;utc=[DateTime]::UtcNow.ToString('o')}
$receipt|ConvertTo-Json -Depth 5|Set-Content "$export\receipt.json"
$receipt|ConvertTo-Json -Depth 5
