#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($env:COMPUTERNAME -notin @('FORUM01', 'MAIL01')) {
    throw 'Run this installer only on FORUM01 or MAIL01.'
}
if (Test-Path 'C:\aeacus') {
    throw 'C:\aeacus already exists and requires inspection before replacement.'
}
if (Get-Service -Name CSSClient -ErrorAction SilentlyContinue) {
    throw 'A CSSClient scoring service already exists.'
}

$archive = Join-Path $PSScriptRoot 'aeacus-win32-v2.1.1.zip'
$expectedHash = 'F5056D0808200C09FF7433CA082ABF4504836BDB1AC1CAD61F84B8F2894469D4'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Aeacus release archive hash mismatch.'
}

$extractDirectory = Join-Path $PSScriptRoot 'package'
if (Test-Path $extractDirectory) {
    throw 'Unexpected existing extraction directory.'
}
Expand-Archive -LiteralPath $archive -DestinationPath $extractDirectory

New-Item -ItemType Directory -Path 'C:\aeacus' | Out-Null
& icacls.exe 'C:\aeacus' /inheritance:r /grant:r `
    '*S-1-5-32-544:(OI)(CI)F' `
    '*S-1-5-18:(OI)(CI)F' `
    '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Could not secure the Aeacus installation directory.'
}

Copy-Item -Path (Join-Path $extractDirectory 'aeacus-win32\*') `
    -Destination 'C:\aeacus' `
    -Recurse

$versionOutput = & cmd.exe /d /c '"C:\aeacus\aeacus.exe" version 2>&1'
if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch 'aeacus version 2\.1\.1') {
    throw "Aeacus executable version verification failed: $versionOutput"
}

if ((Test-Path 'C:\aeacus\scoring.conf') -or (Test-Path 'C:\aeacus\scoring.dat')) {
    throw 'A scoring configuration was unexpectedly installed.'
}
if (Get-Service -Name CSSClient -ErrorAction SilentlyContinue) {
    throw 'A scoring service was unexpectedly installed.'
}

[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    InstallPath = 'C:\aeacus'
    Version = $versionOutput.Trim()
    ScoringConfigurationPresent = $false
    ScoringServicePresent = $false
} | ConvertTo-Json
