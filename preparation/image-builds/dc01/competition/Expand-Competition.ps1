#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Import-Module ActiveDirectory
$original='C:\ProgramData\SummitCompetitionBuild-20261004-r3'
$root='C:\ProgramData\SummitCompetitionExpansion-20261004'
$public='C:\SummitCompetition';$data='C:\SummitSupply';$payload='C:\ProgramData\SummitCompetition'
if($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong guest'}
if((Get-Content "$original\phase.txt" -Raw).Trim() -ne 'runtime-verified'){throw 'Prior runtime must be verified before expansion'}
if(Test-Path $root){throw 'Existing expansion record; inspect before retry'}
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Build-Competition.ps1",[ref]$tokens,[ref]$errors)
if($errors){throw 'Builder syntax invalid'}
$defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false))
foreach($name in @('Native','Private','Preserve','Probe','State','Score')){$f=@($defs | Where-Object Name -eq $name);if($f.Count -ne 1){throw 'Helper mismatch'};$text=$f[0].Extent.Text;if($name -eq 'Probe'){$text=$text -replace '^function Probe','function BaseProbe'};Invoke-Expression $text}
$meta=Get-Content C:\aeacus\probes\targets.json -Raw | ConvertFrom-Json;$roster=$meta.Roster
$businessHash=(Get-FileHash "$data\Business\inventory.csv").Hash
$testingForensics=$false
$extra=@('share-encryption','share-permission','share-ntfs','automation-acl','uac-consent','uac-desktop','defender','firewall','audit-logon','audit-process','updates','root-trust')
$base=@('casey','drew','privilege','contractor','smb','dns-update','dns-transfer','spooler','registry','logging','persistence','credentials','media','fq1','fq2','fq3')
$checks=$base+$extra
function Probe([string]$Name){if($Name -in $extra){$out=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\aeacus\probes\Check-Extra.ps1 -Check $Name;if($LASTEXITCODE -ne 0){throw "Probe ERROR: $Name"};($out -join "`n").Trim()}else{BaseProbe $Name}}
function SetControl([string]$Name,[bool]$Protected){
 if($Name -notin $extra){State $Name $Protected;return}
 switch($Name){
  'share-encryption' {Set-SmbShare SummitOps -EncryptData $Protected -Force}
  'share-permission' {if($Protected){Revoke-SmbShareAccess SummitOps -AccountName Everyone -Force -ErrorAction SilentlyContinue}else{Grant-SmbShareAccess SummitOps -AccountName Everyone -AccessRight Full -Force | Out-Null}}
  {$_ -in @('share-ntfs','automation-acl')} {$path=if($Name -eq 'share-ntfs'){'C:\SummitSupply\Operations'}else{'C:\SummitSupply\Automation'};$rights=if($Protected){'RX'}else{'M'};Native {icacls.exe $path /grant:r ("*$domainUsers`:(OI)(CI)$rights") /T | Out-Null}}
  'uac-consent' {Set-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System ConsentPromptBehaviorAdmin $(if($Protected){5}else{0})}
  'uac-desktop' {Set-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System PromptOnSecureDesktop $(if($Protected){1}else{0})}
  'defender' {Set-MpPreference -DisableRealtimeMonitoring (-not $Protected);$limit=(Get-Date).AddSeconds(30);do{Start-Sleep -Milliseconds 500;$state=(Get-MpComputerStatus).RealTimeProtectionEnabled}while($state -ne $Protected -and (Get-Date) -lt $limit);if($state -ne $Protected){throw 'Defender effective state timeout'}}
  'firewall' {Set-NetFirewallProfile -Profile Public -Enabled $(if($Protected){'True'}else{'False'})}
  {$_ -in @('audit-logon','audit-process')} {$guid=if($Name -eq 'audit-logon'){'{0CCE9215-69AE-11D9-BED3-505054503030}'}else{'{0CCE922B-69AE-11D9-BED3-505054503030}'};$enabled=if($Protected){'enable'}else{'disable'};Native {auditpol.exe /set "/subcategory:$guid" "/success:$enabled" "/failure:$enabled" | Out-Null}}
  'updates' {if($Protected){Set-Service wuauserv -StartupType Manual}else{Stop-Service wuauserv -Force;Set-Service wuauserv -StartupType Disabled}}
  'root-trust' {if($Protected){$cert=Get-Item ("Cert:\LocalMachine\Root\"+$thumb) -ErrorAction SilentlyContinue;if($cert){Remove-Item -LiteralPath $cert.PSPath}}else{Import-Certificate -FilePath "$root\scenario-root.cer" -CertStoreLocation Cert:\LocalMachine\Root | Out-Null}}
 }
}
function Preservation {
 Preserve
 $records=Get-Content C:\ProgramData\SummitLab\Private\initial-domain-credentials.json -Raw | ConvertFrom-Json
 $employee=@($records | Where-Object Sam -eq 'emma.wilson')
 if($employee.Count -ne 1){throw 'Operations test credential missing'}
 $credential=New-Object Management.Automation.PSCredential('CORP\emma.wilson',(ConvertTo-SecureString $employee[0].Password -AsPlainText -Force))
 $drive='OpsProbe'+[guid]::NewGuid().ToString('N').Substring(0,8)
 try{New-PSDrive -Name $drive -PSProvider FileSystem -Root '\\DC01\SummitOps' -Credential $credential | Out-Null;if(-not (Test-Path ($drive+':\inventory.csv'))){throw 'Operations share unavailable under employee authentication'}}finally{Remove-PSDrive -Name $drive -ErrorAction SilentlyContinue}
 if((Get-FileHash 'C:\SummitSupply\Operations\inventory.csv').Hash -ne $opsHash){throw 'Operations content modified'}
 if((Get-FileHash 'C:\SummitSupply\Automation\inventory-maintenance.cmd').Hash -ne $maintenanceHash){throw 'Maintenance payload modified'}
 $t=Get-ScheduledTask SummitInventoryMaintenance;if($t.State -eq 'Disabled' -or $t.Principal.UserId -notin @('S-1-5-19','LOCAL SERVICE','NT AUTHORITY\LOCAL SERVICE')){throw 'Maintenance task unavailable or identity changed'}
}
Preserve
foreach($id in $base){if((Probe $id) -ne 'FAIL'){throw 'Prior starting state mismatch'}}
foreach($p in @('C:\SummitSupply\Operations','C:\SummitSupply\Automation')){if(Test-Path $p){throw 'Scenario directory conflict'}}
if(Get-SmbShare SummitOps -ErrorAction SilentlyContinue){throw 'Share identity conflict'}
if(Get-ScheduledTask SummitInventoryMaintenance -ErrorAction SilentlyContinue){throw 'Task identity conflict'}
New-Item $root -ItemType Directory | Out-Null;Private $root
New-Item "$root\answers" -ItemType Directory | Out-Null
Copy-Item "$original\organizer-answers.json","$original\evidence-payload.cmd" $root
$answers=Get-Content "$root\organizer-answers.json" -Raw | ConvertFrom-Json
$questions=@{};foreach($i in 1..3){$body=Get-Content "$public\Forensic Question $i.txt" -Raw;$parts=[regex]::Split($body,'\r?\nAnswer:\s*\r?\n',2);if($parts.Count -ne 2 -or $parts[1].Trim()){throw 'Public answer not blank'};$questions["fq$i"]=$parts[0];Copy-Item "$public\Forensic Question $i.txt" "$root\answers"}
$p=Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System
$saved=[ordered]@{Machine='DC01';Consent=$p.ConsentPromptBehaviorAdmin;SecureDesktop=$p.PromptOnSecureDesktop;RealtimeDisabled=(Get-MpPreference).DisableRealtimeMonitoring;FirewallPublic=(Get-NetFirewallProfile Public).Enabled.ToString();UpdateStart=(Get-Service wuauserv).StartType.ToString();UpdateStatus=(Get-Service wuauserv).Status.ToString();SharePreviouslyPresent=$false;TaskPreviouslyPresent=$false}
$audit=@();foreach($guid in @('{0CCE9215-69AE-11D9-BED3-505054503030}','{0CCE922B-69AE-11D9-BED3-505054503030}')){$csv=& auditpol.exe /get "/subcategory:$guid" /r;if($LASTEXITCODE -ne 0){throw 'Audit preflight failed'};$row=$csv | Where-Object {$_ -and $_.Trim()} | ConvertFrom-Csv | Where-Object {$_.'Subcategory GUID' -eq $guid};$audit+=[pscustomobject]@{GUID=$guid;Inclusion=$row.'Inclusion Setting'}};$saved.Audit=$audit
$saved | ConvertTo-Json | Set-Content "$root\baseline.json"
Native {auditpol.exe /backup "/file:$root\audit-before.csv" | Out-Null}
Copy-Item C:\aeacus\scoring.dat "$root\previous-scoring.dat"
Copy-Item "$original\scoring.conf" "$root\previous-scoring.conf"
Copy-Item "$original\manifest.json" "$root\previous-manifest.json"
Copy-Item "$public\README.txt" "$root\previous-readme.txt"
Copy-Item "$PSScriptRoot\Recover-Expansion.ps1" "$root\Recover-Expansion.ps1"
Copy-Item $PSCommandPath "$root\Expand-Competition.ps1"
Set-Content "$root\phase.txt" 'baseline-saved'
Stop-Service CSSClient
try{
 $domainUsers="$((Get-ADDomain).DomainSID)-513"
 foreach($path in @('C:\SummitSupply\Operations','C:\SummitSupply\Automation')){New-Item $path -ItemType Directory | Out-Null;Native {icacls.exe $path /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' ("*$domainUsers`:(OI)(CI)RX") '*S-1-5-19:(OI)(CI)RX' | Out-Null}}
 Copy-Item "$data\Business\inventory.csv" 'C:\SummitSupply\Operations\inventory.csv';$opsHash=(Get-FileHash 'C:\SummitSupply\Operations\inventory.csv').Hash
 '@echo off','echo Synthetic inventory maintenance marker.>C:\ProgramData\SummitCompetition\inventory-maintenance.txt','exit /b 0' | Set-Content 'C:\SummitSupply\Automation\inventory-maintenance.cmd' -Encoding ascii
 $maintenanceHash=(Get-FileHash 'C:\SummitSupply\Automation\inventory-maintenance.cmd').Hash
 New-SmbShare -Name SummitOps -Path 'C:\SummitSupply\Operations' -FullAccess 'BUILTIN\Administrators' -ReadAccess 'CORP\Domain Users' -EncryptData $true | Out-Null
 $action=New-ScheduledTaskAction -Execute C:\Windows\System32\cmd.exe -Argument '/d /c C:\SummitSupply\Automation\inventory-maintenance.cmd'
 $principal=New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount -RunLevel Limited
 Register-ScheduledTask SummitInventoryMaintenance -Action $action -Principal $principal -Trigger (New-ScheduledTaskTrigger -Daily -At '05:41') -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 10)) | Out-Null
 $cert=New-SelfSignedCertificate -Type Custom -Subject 'CN=Summit Legacy Training Root 20261004' -CertStoreLocation Cert:\LocalMachine\My -KeyUsage CertSign,CRLSign,DigitalSignature -TextExtension @('2.5.29.19={critical}{text}ca=1') -NotAfter (Get-Date).AddYears(1)
 $thumb=$cert.Thumbprint
 Set-Content "$root\root-thumbprint.txt" $thumb
 Export-Certificate -Cert $cert -FilePath "$root\scenario-root.cer" | Out-Null
 Remove-Item -LiteralPath ("Cert:\LocalMachine\My\"+$thumb) -DeleteKey
 Set-Content "$root\root-thumbprint.txt" $thumb
 $portable=@($roster | ForEach-Object {[pscustomobject]@{SID=$_.SID;Account=$_.Account;Role=$_.Role}})
 [pscustomobject]@{RootThumbprint=$thumb;Roster=$portable} | ConvertTo-Json -Depth 5 | Set-Content C:\aeacus\probes\extras.json
 Copy-Item "$PSScriptRoot\Check-Extra.ps1" C:\aeacus\probes
 Private C:\aeacus\probes
 Add-Content "$public\README.txt" @('','Expanded image: 25 vulnerabilities plus 3 forensic questions; 28 checks, 100 points.','Keep all firewall profiles enabled, Defender real-time protection enabled, and Windows Update service available.','Preserve the file-specific official scorer exception at C:\aeacus\phocus.exe.','Require administrator elevation consent on the secure desktop; keep UAC enabled.','Audit Logon and Process Creation success and failure.','SummitOps share and Operations inventory are required: SMB encryption required; Domain Users read only.','Domain users must not modify Operations files or Automation scripts; preserve inventory data.','Keep SummitInventoryMaintenance enabled as LOCAL SERVICE; its supplied script writes only a harmless marker.','The unauthorized legacy training root CA must not remain trusted. Preserve legitimate certificate trust.','Forensic evidence and all three blank answer files must remain available.')
 (Get-Content "$public\README.txt" -Raw).Replace('Local Aeacus score: 16 checks, 100 points.','Local Aeacus score: 28 checks, 100 points.') | Set-Content "$public\README.txt"
 $results=New-Object 'System.Collections.Generic.List[object]'
 foreach($entry in (Get-Content "$original\rehearsals.json" -Raw | ConvertFrom-Json)){$results.Add($entry)}
 Set-Content "$root\phase.txt" 'rehearsing'
 foreach($id in $extra){
  SetControl $id $true;if((Probe $id) -ne 'PASS'){throw "Protected failure: $id"};Preservation
  SetControl $id $false;if((Probe $id) -ne 'FAIL'){throw "Planted failure: $id"};Preservation
  SetControl $id $true;if((Probe $id) -ne 'PASS'){throw "Repair failure: $id"};Preservation
  SetControl $id $false;if((Probe $id) -ne 'FAIL'){throw "Final failure: $id"};Preservation
  $results.Add([pscustomobject]@{Control=$id;Protected='PASS';Planted='FAIL';Repaired='PASS';Final='FAIL';Preservation='PASS';Time=(Get-Date).ToString('o')})
  $results | ConvertTo-Json -Depth 5 | Set-Content "$root\rehearsals.json"
  "Rehearsed extra $id"
 }
 $old=Get-Content "$original\scoring.conf" -Raw
 $config=$old -replace 'points = 5','points = 3' -replace 'points = 10','points = 3'
 # Forensic questions retain 10, 10, 5 points; each real weakness is 3 points.
 foreach($id in @('fq1','fq2','fq3')){$pts=if($id -eq 'fq3'){5}else{10};$pattern='(?s)(\[\[check\]\]\s*message = "Forensic question '+$id.Substring(2)+' answered"\s*points = )3';$config=[regex]::Replace($config,$pattern,('${1}'+$pts))}
 foreach($id in $extra){$config+="`r`n[[check]]`r`nmessage = `"$id policy repaired`"`r`npoints = 3`r`n[[check.pass]]`r`ntype = 'CommandOutput'`r`ncmd = '& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\aeacus\probes\Check-Extra.ps1 -Check $id'`r`nvalue = 'PASS'`r`n"}
 $pointTotal=0;foreach($match in [regex]::Matches($config,'(?m)^points = (\d+)')){$pointTotal+=[int]$match.Groups[1].Value}
 if($pointTotal -ne 100 -or [regex]::Matches($config,'(?m)^\[\[check\]\]').Count -ne 28){throw 'Expanded totals mismatch'}
 $config | Set-Content "$root\scoring.conf" -Encoding ascii
 Copy-Item "$root\scoring.conf" C:\aeacus\scoring.conf;Private C:\aeacus\scoring.conf
 Push-Location C:\aeacus;try{Native {& .\aeacus.exe check *> "$root\check.log"}}finally{Pop-Location}
 foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Combined starting mismatch: $id"}}
 Score 0 starting
 $testingForensics=$true
 foreach($id in $checks){SetControl $id $true};Preservation
 foreach($id in $checks){if((Probe $id) -ne 'PASS'){throw "Combined solution mismatch: $id"}}
 Score 100 solution
 foreach($id in $checks){SetControl $id $false};Preservation
 $testingForensics=$false
 foreach($id in $checks){if((Probe $id) -ne 'FAIL'){throw "Combined restoration mismatch: $id"}}
 Score 0 restored
 $results | ConvertTo-Json -Depth 5 | Set-Content "$root\rehearsals.json"
 Push-Location C:\aeacus;try{Native {& .\aeacus.exe encrypt *> "$root\encrypt.log"}}finally{Pop-Location}
 Private C:\aeacus\scoring.dat;Remove-Item -LiteralPath C:\aeacus\scoring.conf;Remove-Item -LiteralPath C:\aeacus\assets\ScoringReport.html
 $start=Get-Date;Start-Service CSSClient;$deadline=(Get-Date).AddMinutes(5);$ok=$false
 do{Start-Sleep -Seconds 3;if((Get-Service CSSClient).Status -ne 'Running'){throw 'Scorer stopped'};$f=Get-Item C:\aeacus\assets\ScoringReport.html -ErrorAction SilentlyContinue;if($f -and $f.LastWriteTime -ge $start){$html=Get-Content $f.FullName -Raw;if($html -match '0 out of 100 points received' -and $html -match '</html>'){$ok=$true;break}}}while((Get-Date) -lt $deadline)
 if(-not $ok){throw 'Expanded encrypted runtime deadline exceeded'}
 Preservation
 $manifest=[ordered]@{Machine='DC01';Domain='corp.summit.test';OS='Windows Server 2022 Standard build 20348';Vulnerabilities=25;ForensicQuestions=3;Checks=28;Points=100;Starting=0;Solution=100;Restored=0;BaseProbeHash=(Get-FileHash C:\aeacus\probes\Check-Competition.ps1).Hash;ExtraProbeHash=(Get-FileHash C:\aeacus\probes\Check-Extra.ps1).Hash;ConfigHash=(Get-FileHash "$root\scoring.conf").Hash;EncryptedRuntime='PASS';ManualDesktop='PENDING';Reboot='PENDING';RecoveryAcceptance='PENDING';Export='PENDING';BaselineSnapshot='Pre-Competition-DC01-20261004';RootThumbprint=$thumb;Time=(Get-Date).ToString('o')}
 $manifest | ConvertTo-Json -Depth 5 | Set-Content "$root\manifest.json"
 $issueRecords=@();foreach($id in $checks){$category=if($id -like 'fq*'){'Forensics Questions'}elseif($id -in @('casey','drew','privilege','contractor')){'User Auditing'}elseif($id -in @('spooler','registry')){'Service Auditing'}elseif($id -in @('credentials','media')){'Prohibited Files'}elseif($id -eq 'persistence'){'Malware'}elseif($id -in @('defender','firewall')){'Defensive Countermeasures'}elseif($id -eq 'updates'){'Operating System Updates'}elseif($id -in @('logging','audit-logon','audit-process','uac-consent','uac-desktop')){'Local Policy'}else{'Application Security'};$points=if($id -in @('fq1','fq2')){10}elseif($id -eq 'fq3'){5}else{3};$issueRecords+=[pscustomobject]@{ID=$id;Category=$category;Points=$points;Target=$id;PlantedState='Native FAIL in final participant state';Repair='Meet the corresponding required-protection rule in DC01 README';Probe=if($id -in $extra){"Check-Extra.ps1 -Check $id"}else{"Check-Competition.ps1 -Check $id"};Outcomes=@('PASS','FAIL','ERROR');Dependencies=@('AD','DNS','roster','required data');Preserve=@('employee authentication','business inventory','required services','legitimate maintenance','organizer SSH');Recovery='Pre-Competition-DC01-20261004 snapshot plus original baseline and scoped Recover-Expansion.ps1';Status='runtime-verified';Evidence=@('protected PASS','planted FAIL','repaired PASS','final FAIL','combined 0/100,100/100,0/100','fresh Phocus 0/100')}}
 $issueRecords | ConvertTo-Json -Depth 5 | Set-Content "$root\issues.json"
 Set-Content "$root\phase.txt" 'runtime-verified'
 'Expanded DC01 runtime verified: 25 vulnerabilities plus 3 forensic questions; 28 checks; scores 0/100, 100/100, 0/100.'
}catch{$_ | Out-String | Set-Content "$root\failure.txt";Set-Content "$root\phase.txt" 'failed-requires-scoped-recovery';throw}
