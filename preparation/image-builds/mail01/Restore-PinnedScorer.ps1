# Run ONLY after explicit user approval of this exact MAIL01 executable exclusion.
#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'This approval is scoped to MAIL01'}
$archive=Join-Path $PSScriptRoot 'aeacus-win32-v2.1.1.zip'
$archiveHash='F5056D0808200C09FF7433CA082ABF4504836BDB1AC1CAD61F84B8F2894469D4'
$runtimeHash='BF266B0E2BFCCB6AA871D61D2D9584ACBB2B11D19D5598E4435C78294A57DD4A'
if((Get-FileHash -LiteralPath $archive).Hash -ne $archiveHash){throw 'Pinned release archive mismatch'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead($archive)
try{
 $entry=@($zip.Entries|Where-Object FullName -eq 'aeacus-win32/phocus.exe')
 if($entry.Count -ne 1){throw 'Unexpected runtime archive entry'}
 $stream=$entry[0].Open();$hasher=[Security.Cryptography.SHA256]::Create()
 try{$hash=([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','');if($hash -ne $runtimeHash){throw 'Archive-contained runtime mismatch'}}finally{$stream.Dispose();$hasher.Dispose()}
 $record='C:\ProgramData\SummitLab\MailScorerRecovery-'+[guid]::NewGuid().ToString('N')
 New-Item -ItemType Directory -Path $record|Out-Null
 & icacls.exe $record /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F'|Out-Null;if($LASTEXITCODE){throw 'Private recovery ACL failed'}
 [ordered]@{exclusionPaths=@((Get-MpPreference).ExclusionPath);realTimeProtection=(Get-MpComputerStatus).RealTimeProtectionEnabled;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content "$record\before.json"
 Add-MpPreference -ExclusionPath 'C:\aeacus\phocus.exe'
 if(@((Get-MpPreference).ExclusionPath) -notcontains 'C:\aeacus\phocus.exe'){throw 'Exact approved exclusion was not applied'}
 if(-not(Get-MpComputerStatus).RealTimeProtectionEnabled){throw 'Defender protection is not active'}
 # Preference writes propagate asynchronously; confirm the active engine before extraction.
 $deadline=(Get-Date).AddSeconds(30)
 do{
  & 'C:\Program Files\Windows Defender\MpCmdRun.exe' -CheckExclusion -Path 'C:\aeacus\phocus.exe'|Out-Null
  $excluded=($LASTEXITCODE -eq 0)
  if(-not$excluded){Start-Sleep -Seconds 2}
 }until($excluded -or (Get-Date) -gt $deadline)
 if(-not$excluded){throw 'The active Defender engine has not applied the approved exclusion'}
 if(Test-Path C:\aeacus\phocus.exe){if((Get-FileHash C:\aeacus\phocus.exe).Hash -ne $runtimeHash){throw 'Existing target hash mismatch; do not overwrite'}}
 else{[IO.Compression.ZipFileExtensions]::ExtractToFile($entry[0],'C:\aeacus\phocus.exe',$false)}
 if((Get-FileHash C:\aeacus\phocus.exe).Hash -ne $runtimeHash){throw 'Restored runtime hash mismatch'}
 [ordered]@{machine='MAIL01';approvedExclusion='C:\aeacus\phocus.exe';sha256=$runtimeHash;defenderRealTime=$true;record=$record;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content "$record\receipt.json"
 Get-Content "$record\receipt.json"
}finally{$zip.Dispose()}
