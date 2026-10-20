param([Parameter(Mandatory=$true)][string]$ExportRoot,[Parameter(Mandatory=$true)][string]$ArchiveHash)
#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
if($ExportRoot -notmatch '^C:\\ProgramData\\SummitLab\\MailOrganizerExport-[a-f0-9]{32}$' -or $ArchiveHash -notmatch '^[A-Fa-f0-9]{64}$'){throw 'Invalid exact export identity'}
$receipt=Get-Content "$ExportRoot\receipt.json" -Raw|ConvertFrom-Json
if($receipt.exportRoot -ne $ExportRoot -or $receipt.sha256 -ne $ArchiveHash -or (Get-FileHash "$ExportRoot\organizer-records.zip").Hash -ne $ArchiveHash){throw 'Verified external archive identity mismatch'}
$current=(Get-Content C:\ProgramData\SummitLab\MailCompetition-current.txt -Raw).Trim()
if($current -notmatch '^C:\\ProgramData\\SummitLab\\MailCompetition-[a-f0-9]{32}$' -or (Get-Content "$current\status.json" -Raw|ConvertFrom-Json).phase -ne 'runtime-verified'){throw 'Current build incomplete'}
. C:\aeacus\probes\Probe.ps1
foreach($id in Get-ControlIds){if((Invoke-MailCheck $id) -ne 'FAIL'){throw 'Final challenge changed before archival cleanup'}}
$allowed=@($current,'C:\ProgramData\SummitLab\MailBuild-20261004','C:\ProgramData\SummitLab\MailCompetition-d1804031f863415093e5ef70fb1b3b4f','C:\ProgramData\SummitLab\MailCompetition-e6fa7807bc714eaab3ba8ebd964714d3','C:\ProgramData\SummitLab\MailRuntimePreflight-3cf54f3b7dda4ccbb0ddd686ccbfbd33')
$sources=@($receipt.sourceRoots)
foreach($p in $allowed){if($sources -notcontains $p){throw 'Required recovery record missing from archive manifest'}}
foreach($p in $sources){
 if($allowed -notcontains $p -and $p -notmatch '^C:\\ProgramData\\SummitLab\\MailScorerRecovery-[a-f0-9]{32}$'){throw 'Unrecognized cleanup scope'}
 if((Resolve-Path -LiteralPath $p).Path -ne $p){throw 'Resolved cleanup path mismatch'}
 if((Get-Item -LiteralPath $p).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse cleanup root'}
 if(@(Get-ChildItem -LiteralPath $p -Recurse -Force|Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Reparse artifact inside cleanup root'}
}
if((Resolve-Path -LiteralPath $ExportRoot).Path -ne $ExportRoot){throw 'Export cleanup path mismatch'}
if((Get-Item -LiteralPath $ExportRoot).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse export root'}
if(@(Get-ChildItem -LiteralPath $ExportRoot -Recurse -Force|Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Reparse artifact inside export root'}
# Remove only organizer tasks created by these build records. Preserve the planted scenario task.
$tasks=@('BuildMAIL01-20261004')
foreach($p in @($current,'C:\ProgramData\SummitLab\MailCompetition-e6fa7807bc714eaab3ba8ebd964714d3')){if(Test-Path "$p\build-task.txt"){$tasks+=@(Get-Content "$p\build-task.txt")}}
foreach($name in $tasks){
 if($name -ne 'BuildMAIL01-20261004' -and $name -notmatch '^BuildMAIL01-[a-f0-9]{32}$'){throw 'Unrecognized organizer task'}
 $t=Get-ScheduledTask -TaskPath '\SummitOrganizer\' -TaskName $name -ErrorAction SilentlyContinue
 if($t){if($t.State -eq 'Running'){throw 'Build task is still running'};Unregister-ScheduledTask -InputObject $t -Confirm:$false}
}
foreach($p in $sources){Remove-Item -LiteralPath $p -Recurse -Force}
Remove-Item -LiteralPath C:\ProgramData\SummitLab\MailCompetition-current.txt
# The separate export directory was hash-verified above and is also an exact owned directory.
Remove-Item -LiteralPath $ExportRoot -Recurse -Force
[ordered]@{machine='MAIL01';organizerArchiveSha256=$ArchiveHash;removedBuildRoots=$sources;runtimePreserved=$true;challengePreserved=$true;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 5
