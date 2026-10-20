#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'FORUM01'){throw 'Wrong guest'}
$root='C:\ProgramData\SummitLab\ForumCompetition-20261004'
$source='C:\ProgramData\SummitLab\ForumCompetitionSource-20261004'
$zip=Join-Path $source 'aeacus-win32-v2.1.1.zip'
if((Get-FileHash $zip).Hash -ne 'F5056D0808200C09FF7433CA082ABF4504836BDB1AC1CAD61F84B8F2894469D4'){throw 'Pinned release archive mismatch'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=[IO.Compression.ZipFile]::OpenRead($zip)
try {
 $entry=$archive.GetEntry('aeacus-win32/phocus.exe')
 if(-not $entry -or $entry.Length -ne 8340992){throw 'Pinned runtime entry mismatch'}
 $stream=$entry.Open();$memory=New-Object IO.MemoryStream
 try{$stream.CopyTo($memory);$bytes=$memory.ToArray()}finally{$stream.Dispose();$memory.Dispose()}
} finally {$archive.Dispose()}
$sha=[Security.Cryptography.SHA256]::Create()
try {$hash=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','')}finally{$sha.Dispose()}
if($hash -ne 'BF266B0E2BFCCB6AA871D61D2D9584ACBB2B11D19D5598E4435C78294A57DD4A'){throw 'Pinned runtime content mismatch'}
# A single required scoring executable is allowed; all other Defender scanning remains enabled.
Add-MpPreference -ExclusionPath 'C:\aeacus\phocus.exe'
[IO.File]::WriteAllBytes('C:\aeacus\phocus.exe',$bytes)
if((Get-FileHash C:\aeacus\phocus.exe).Hash -ne $hash){throw 'Restored runtime hash mismatch'}
$service=Get-CimInstance Win32_Service -Filter "Name='CSSClient'"
if($service){if($service.PathName -ne 'C:\aeacus\phocus.exe'){throw 'Unexpected existing scoring service'}}
else{New-Service -Name CSSClient -BinaryPathName 'C:\aeacus\phocus.exe' -DisplayName 'Summit Forum Competition Scoring' -StartupType Automatic | Out-Null}
if(Test-Path C:\aeacus\assets\ScoringReport.html){Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html}
$started=[DateTime]::UtcNow
Start-Service CSSClient
$deadline=(Get-Date).AddMinutes(4)
do {
 Start-Sleep -Seconds 2
 if((Get-Service CSSClient).Status -ne 'Running'){throw 'Pinned encrypted runtime failed'}
 $fresh=$false
 if(Test-Path C:\aeacus\assets\ScoringReport.html){$file=Get-Item C:\aeacus\assets\ScoringReport.html;$html=Get-Content $file.FullName -Raw;$fresh=($file.LastWriteTimeUtc -ge $started -and $html -match '0 out of 100 points received' -and $html -match '</html>')}
}until($fresh -or (Get-Date) -gt $deadline)
if(-not $fresh){throw 'Fresh encrypted report missing after pinned restoration'}
$protection=Get-MpComputerStatus
if(-not $protection.AntivirusEnabled -or -not $protection.RealTimeProtectionEnabled){throw 'Defender protections not active'}
$status=Get-Content "$root\status.json" -Raw | ConvertFrom-Json
$status.phase='runtime-verified';$status.serviceStatus='Running';$status.encryptedReportFresh=$true;$status.reportUtc=$file.LastWriteTimeUtc.ToString('o')
$status | Add-Member -NotePropertyName defenderException -NotePropertyValue 'C:\aeacus\phocus.exe only; pinned Aeacus 2.1.1 SHA-256 verified; antivirus and real-time protection active' -Force
$status | ConvertTo-Json -Depth 5 | Set-Content "$root\status.json" -Encoding UTF8
[ordered]@{service='Running';score=0;total=100;defenderAntivirus=$protection.AntivirusEnabled;defenderRealtime=$protection.RealTimeProtectionEnabled;exception='C:\aeacus\phocus.exe';sha256=$hash;freshReport=$true} | ConvertTo-Json
