#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'FORUM01'){throw 'Wrong guest'}
$parent='C:\ProgramData\SummitLab'
$targets=@('C:\ProgramData\SummitLab\ForumCompetition-20261004','C:\ProgramData\SummitLab\ForumCompetitionSource-20261004')
foreach($target in $targets){
 $resolved=(Resolve-Path -LiteralPath $target).ProviderPath
 if($resolved -ne $target -or (Split-Path $resolved -Parent) -ne $parent){throw 'Cleanup target mismatch'}
 if((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse target forbidden'}
}
if((Get-FileHash ($targets[0]+'\organizer-records.zip')).Hash -ne '9870B5CC569D0DE2B631810453B01C9304519692B7E018232DF8BA1413E07937'){throw 'Archived guest material changed'}
foreach($target in $targets){Remove-Item -LiteralPath $target -Recurse -Force}
foreach($target in $targets){if(Test-Path -LiteralPath $target){throw 'Archived staging remains'}}
[ordered]@{machine='FORUM01';archivedStagingRemoved=$true;organizerArchiveSha256='9870B5CC569D0DE2B631810453B01C9304519692B7E018232DF8BA1413E07937';utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json
