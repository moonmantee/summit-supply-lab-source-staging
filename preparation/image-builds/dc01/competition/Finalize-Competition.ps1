#Requires -RunAsAdministrator
# Resume only the diagnosed Phocus quarantine after successful native rehearsals.
param([switch]$ResumeRuntimeRecovery)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\SummitCompetitionBuild-20261004-r3'
$public='C:\SummitCompetition';$data='C:\SummitSupply';$payload='C:\ProgramData\SummitCompetition'
if($env:COMPUTERNAME -ne 'DC01'){throw 'Wrong guest'}
Import-Module ActiveDirectory
if((Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong domain'}
if((Get-Content "$root\failure.txt" -Raw) -notmatch "Cannot find any service with service name 'CSSClient'"){throw 'Unrecognized runtime failure'}
$service=Get-Service CSSClient -ErrorAction SilentlyContinue
if($service){if(-not $ResumeRuntimeRecovery -or (Get-CimInstance Win32_Service -Filter "Name='CSSClient'").PathName -ne 'C:\aeacus\phocus.exe'){throw 'Unexpected service before recovery'};if($service.Status -eq 'Running'){Stop-Service CSSClient}}
$archive="$PSScriptRoot\aeacus-win32-v2.1.1.zip"
if((Get-FileHash $archive).Hash -ne 'F5056D0808200C09FF7433CA082ABF4504836BDB1AC1CAD61F84B8F2894469D4'){throw 'Pinned archive mismatch'}
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Build-Competition.ps1",[ref]$tokens,[ref]$errors)
if($errors){throw 'Builder syntax invalid'}
$names=@('Native','Private','Hash','Preserve','Probe','State','Score','Recovery')
$definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false))
foreach($name in $names){$function=@($definitions | Where-Object Name -eq $name);if($function.Count -ne 1){throw 'Unexpected function contract'};Invoke-Expression $function[0].Extent.Text}
$meta=Get-Content C:\aeacus\probes\targets.json -Raw | ConvertFrom-Json
$roster=$meta.Roster
if(@($roster).Count -ne 20 -or (Get-ADUser $meta.ContractorSID).SamAccountName -ne 'svc.legacybackup'){throw 'Runtime metadata identity mismatch'}
$businessHash=(Get-FileHash "$data\Business\inventory.csv").Hash
$answers=Get-Content "$root\organizer-answers.json" -Raw | ConvertFrom-Json
$questions=@{}
foreach($i in 1..3){$body=Get-Content "$public\Forensic Question $i.txt" -Raw;$parts=[regex]::Split($body,'\r?\nAnswer:\s*\r?\n',2);if($parts.Count -ne 2 -or $parts[1].Trim()){throw 'Public forensic answer not blank'};$questions["fq$i"]=$parts[0]}
$checks=@('casey','drew','privilege','contractor','smb','dns-update','dns-transfer','spooler','registry','logging','persistence','credentials','media','fq1','fq2','fq3')
$prior=Get-Content "$root\rehearsals.json" -Raw | ConvertFrom-Json
if(@($prior).Count -ne 16 -or @($prior | Where-Object {$_.Protected -ne 'PASS' -or $_.Planted -ne 'FAIL' -or $_.Repaired -ne 'PASS' -or $_.Final -ne 'FAIL' -or $_.Preservation -ne 'PASS'}).Count){throw 'Prior rehearsal evidence mismatch'}
$results=New-Object 'System.Collections.Generic.List[object]'
foreach($entry in $prior){$results.Add($entry)}
$testingForensics=$false
Preserve
foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Runtime starting-state mismatch: $id"}}
Copy-Item "$root\failure.txt" "$root\failure-phocus-quarantine.txt"
$alreadyExcluded='C:\aeacus\phocus.exe' -in (Get-MpPreference).ExclusionPath
$runtimeRecord="$root\runtime-recovery.json"
if((Test-Path $runtimeRecord) -and -not $ResumeRuntimeRecovery){throw 'Runtime recovery record already exists; inspect before retry'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead($archive)
$entry=$zip.Entries | Where-Object FullName -eq 'aeacus-win32/phocus.exe'
$stream=$entry.Open();$digest=[Security.Cryptography.SHA256]::Create()
try{$trustedHash=([BitConverter]::ToString($digest.ComputeHash($stream))).Replace('-','')}finally{$stream.Dispose();$digest.Dispose()}
if($trustedHash -ne 'BF266B0E2BFCCB6AA871D61D2D9584ACBB2B11D19D5598E4435C78294A57DD4A'){throw 'Phocus differs from the pinned archive binary'}
if($ResumeRuntimeRecovery){$record=Get-Content $runtimeRecord -Raw | ConvertFrom-Json;if($record.Hash -ne $trustedHash -or $record.Executable -ne 'C:\aeacus\phocus.exe' -or -not $alreadyExcluded){throw 'Runtime recovery record mismatch'}}else{[pscustomobject]@{Executable='C:\aeacus\phocus.exe';Hash=$trustedHash;ArchiveHash=(Get-FileHash $archive).Hash;DefenderWasEnabled=(Get-MpComputerStatus).AntivirusEnabled;ExclusionPreviouslyPresent=$alreadyExcluded;AddedExclusion=(-not $alreadyExcluded);Reason='Defender quarantined the pinned official Aeacus 2.1.1 production runtime and removed CSSClient';Time=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content $runtimeRecord}
try{
 if(-not $alreadyExcluded){Add-MpPreference -ExclusionPath 'C:\aeacus\phocus.exe'}
 if(-not $ResumeRuntimeRecovery){[IO.Compression.ZipFileExtensions]::ExtractToFile($entry,'C:\aeacus\phocus.exe',$true)}
 $zip.Dispose()
 Private C:\aeacus\phocus.exe
 if((Get-FileHash C:\aeacus\phocus.exe).Hash -ne $trustedHash -or -not (Get-MpComputerStatus).AntivirusEnabled){throw 'Runtime/Defender preservation failed'}
 Copy-Item "$root\scoring.conf" C:\aeacus\scoring.conf
 Private C:\aeacus\scoring.conf
 Score 0 starting-after-runtime-recovery
 $results | ConvertTo-Json -Depth 6 | Set-Content "$root\runtime-rehearsals.json"
 $testingForensics=$true
 foreach($id in $checks){State $id $true};Preserve
 foreach($id in $checks){if((Probe $id) -ne 'PASS'){throw "Solution mismatch: $id"}}
 Score 100 solution
 $results | ConvertTo-Json -Depth 6 | Set-Content "$root\runtime-rehearsals.json"
 foreach($id in $checks){State $id $false};Preserve
 $testingForensics=$false
 foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Restored mismatch: $id"}}
 Score 0 restored-after-runtime-recovery
 $results | ConvertTo-Json -Depth 6 | Set-Content "$root\runtime-rehearsals.json"
 Push-Location C:\aeacus;try{Native {& .\aeacus.exe encrypt *> "$root\encrypt-runtime-recovery.log"}}finally{Pop-Location}
 Private C:\aeacus\scoring.dat
 Remove-Item -LiteralPath C:\aeacus\scoring.conf
 Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html
 if(-not (Get-Service CSSClient -ErrorAction SilentlyContinue)){New-Service CSSClient -BinaryPathName 'C:\aeacus\phocus.exe' -DisplayName 'Summit DC01 Competition Scoring' -StartupType Automatic | Out-Null}else{Set-Service CSSClient -StartupType Automatic}
 $start=Get-Date;Start-Service CSSClient
 $deadline=(Get-Date).AddMinutes(5);$verified=$false
 do{
  Start-Sleep -Seconds 3
  if((Get-Service CSSClient).Status -ne 'Running'){throw 'Scoring service stopped'}
  $report=Get-Item C:\aeacus\assets\ScoringReport.html -ErrorAction SilentlyContinue
  if($report -and $report.LastWriteTime -ge $start){$html=Get-Content $report.FullName -Raw;if($html -match '0 out of 100 points received' -and $html -match '</html>'){$verified=$true;break}}
 }while((Get-Date) -lt $deadline)
 if(-not $verified){throw 'Fresh encrypted report deadline exceeded'}
 Preserve
 $config=Get-Content "$root\scoring.conf" -Raw
 if([regex]::Matches($config,'(?m)^\[\[check\]\]').Count -ne 16){throw 'Config count mismatch'}
 $issues=@();$blocks=[regex]::Matches($config,'(?s)\[\[check\]\](.*?)(?=\[\[check\]\]|\z)')
 for($i=0;$i -lt 16;$i++){
  $id=$checks[$i];$block=$blocks[$i].Groups[1].Value
  $category=switch($id){{$_ -in @('casey','drew','privilege','contractor')}{'User Auditing'};{$_ -in @('smb','dns-update','dns-transfer')}{'Application Security'};{$_ -in @('spooler','registry')}{'Service Auditing'};'logging'{'Local Policy'};'persistence'{'Malware'};{$_ -in @('credentials','media')}{'Prohibited Files'};default{'Forensics Questions'}}
  $issues+=[pscustomobject]@{ID=$id;Category=$category;Points=[int][regex]::Match($block,'points = (\d+)').Groups[1].Value;Target=$id;PlantedState='Observable final FAIL recorded by the native probe';Repair=[regex]::Match($block,'message = "([^"]+)"').Groups[1].Value;Policy='DC01 README required protection';Probe="Check-Competition.ps1 -Check $id";Outcomes=@('PASS','FAIL','ERROR');Dependencies=@('directory','DNS','named roster');Preserve=@('employee authentication','directory shares','business inventory','organizer SSH');Recovery='baseline.json, runtime-recovery.json, Recovery function, pre-build VMware snapshot';Status='runtime-verified';Evidence=@('protected PASS','planted FAIL','repaired PASS','final planted FAIL','combined 0/100,100/100,0/100','fresh Phocus 0/100')}
 }
 $manifest=[ordered]@{Machine='DC01';OS='Windows Server 2022 Standard build 20348';Domain='corp.summit.test';Address='10.77.40.10';Snapshot='Pre-Competition-DC01-20261004';Engine='Aeacus 2.1.1';Count=16;Points=100;StartingScore=0;SolutionScore=100;RestoredScore=0;ProbeSHA256=(Get-FileHash C:\aeacus\probes\Check-Competition.ps1).Hash;ConfigSHA256=(Get-FileHash "$root\scoring.conf").Hash;RuntimeSHA256=$trustedHash;DefenderEnabled=$true;ScorerFileExclusion='C:\aeacus\phocus.exe';Acceptance=@{Automated='PASS';Desktop='PENDING';Reboot='PENDING';SnapshotRestore='PENDING';Export='PENDING'};OrganizerBoundary='Construction/solution/recovery records remain guest-private; archive outside participant export before release';Time=(Get-Date).ToString('o')}
 $manifest | ConvertTo-Json -Depth 6 | Set-Content "$root\manifest.json"
 $issues | ConvertTo-Json -Depth 6 | Set-Content "$root\issues.json"
 Set-Content "$root\phase.txt" 'runtime-verified'
 'Encrypted Phocus runtime verified; 16 checks; starting 0/100; solution 100/100; restored 0/100. Defender remains enabled with a file-specific scorer exception.'
}catch{$_ | Out-String | Set-Content ("$root\runtime-failure-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.txt');throw}
