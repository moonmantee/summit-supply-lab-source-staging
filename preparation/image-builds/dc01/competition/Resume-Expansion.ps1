#Requires -RunAsAdministrator
# Resume only the diagnosed certificate-export parameter error. Reuse the reviewed
# builder's exact tail and functions; never recreate identities or recovery records.
param([switch]$ResumeProbeCopy,[switch]$ResumeRemaining)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Import-Module ActiveDirectory
$original='C:\ProgramData\SummitCompetitionBuild-20261004-r3'
$root='C:\ProgramData\SummitCompetitionExpansion-20261004'
$public='C:\SummitCompetition';$data='C:\SummitSupply';$payload='C:\ProgramData\SummitCompetition'
if($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test'){throw 'Wrong guest'}
if((Get-Content "$root\failure.txt" -Raw) -notmatch '(?s)Export-Certificate.*PositionalParameterNotFound'){throw 'Unrecognized expansion failure'}
foreach($r in (Get-Acl $root).Access){if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Untrusted recovery ACL'}}
Copy-Item "$root\failure.txt" "$root\failure-certificate-export.txt"
$tokens=$null;$errors=$null;$builder=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Build-Competition.ps1",[ref]$tokens,[ref]$errors);if($errors){throw 'Base syntax invalid'}
$defs=@($builder.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false))
foreach($name in @('Native','Private','Preserve','Probe','State','Score')){$f=@($defs | Where-Object Name -eq $name);if($f.Count -ne 1){throw 'Base helper mismatch'};$text=$f[0].Extent.Text;if($name -eq 'Probe'){$text=$text -replace '^function Probe','function BaseProbe'};Invoke-Expression $text}
$ast=[Management.Automation.Language.Parser]::ParseFile("$PSScriptRoot\Expand-Competition.ps1",[ref]$tokens,[ref]$errors);if($errors){throw 'Expansion syntax invalid'}
$defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false));foreach($name in @('Probe','SetControl','Preservation')){$f=@($defs | Where-Object Name -eq $name);if($f.Count -ne 1){throw 'Expansion helper mismatch'};Invoke-Expression $f[0].Extent.Text}
$meta=Get-Content C:\aeacus\probes\targets.json -Raw | ConvertFrom-Json;$roster=$meta.Roster
$businessHash=(Get-FileHash "$data\Business\inventory.csv").Hash
$opsHash=(Get-FileHash 'C:\SummitSupply\Operations\inventory.csv').Hash
$maintenanceHash=(Get-FileHash 'C:\SummitSupply\Automation\inventory-maintenance.cmd').Hash
$domainUsers="$((Get-ADDomain).DomainSID)-513"
$answers=Get-Content "$root\organizer-answers.json" -Raw | ConvertFrom-Json
$questions=@{};foreach($i in 1..3){$body=Get-Content "$public\Forensic Question $i.txt" -Raw;$parts=[regex]::Split($body,'\r?\nAnswer:\s*\r?\n',2);if($parts.Count -ne 2 -or $parts[1].Trim()){throw 'Public answer changed'};$questions["fq$i"]=$parts[0]}
$extra=@('share-encryption','share-permission','share-ntfs','automation-acl','uac-consent','uac-desktop','defender','firewall','audit-logon','audit-process','updates','root-trust')
$base=@('casey','drew','privilege','contractor','smb','dns-update','dns-transfer','spooler','registry','logging','persistence','credentials','media','fq1','fq2','fq3');$checks=$base+$extra;$testingForensics=$false
if((Get-Service CSSClient).Status -ne 'Stopped'){throw 'Scorer not stopped at prepared checkpoint'}
if(-not $ResumeRemaining -and (-not (Get-SmbShare SummitOps).EncryptData -or @(Get-SmbShareAccess SummitOps | Where-Object AccountName -eq 'Everyone').Count)){throw 'Prepared share state mismatch'}
if($ResumeProbeCopy -or $ResumeRemaining){
 $latest=Get-ChildItem "$root\failure-resume-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
 $expected=if($ResumeRemaining){'(?s)GpoBoolean.*ParameterArgumentTransformationError'}else{'Cannot find path.*Check-Extra.ps1'}
 if(-not $latest -or (Get-Content $latest.FullName -Raw) -notmatch $expected){throw 'Unrecognized expansion resume failure'}
 $thumb=(Get-Content "$root\root-thumbprint.txt" -Raw).Trim()
 $cert=New-Object Security.Cryptography.X509Certificates.X509Certificate2("$root\scenario-root.cer")
 if($cert.Thumbprint -ne $thumb -or $cert.Subject -ne 'CN=Summit Legacy Training Root 20261004'){throw 'Prepared certificate mismatch'}
}else{$certs=@(Get-ChildItem Cert:\LocalMachine\My | Where-Object Subject -eq 'CN=Summit Legacy Training Root 20261004');if($certs.Count -ne 1){throw 'Prepared certificate identity mismatch'};$cert=$certs[0];$thumb=$cert.Thumbprint}
if(Get-Item ("Cert:\LocalMachine\Root\"+$thumb) -ErrorAction SilentlyContinue){throw 'Certificate unexpectedly trusted before rehearsal'}
Set-Content "$root\root-thumbprint.txt" $thumb
Preservation
foreach($id in $base){if((Probe $id) -ne 'FAIL'){throw 'Prepared base score mismatch'}}
$main=@($ast.EndBlock.Statements | Where-Object {$_ -is [Management.Automation.Language.TryStatementAst]});if($main.Count -ne 1){throw 'Unexpected expansion control flow'}
$statements=@($main[0].Body.Statements);$start=-1;for($i=0;$i -lt $statements.Count;$i++){if(($ResumeRemaining -and $statements[$i].Extent.Text -like 'foreach($id in $extra)*' -and $statements[$i].Extent.Text -match 'Protected failure') -or (-not $ResumeRemaining -and -not $ResumeProbeCopy -and $statements[$i].Extent.Text -like 'Export-Certificate -Cert*') -or (-not $ResumeRemaining -and $ResumeProbeCopy -and $statements[$i].Extent.Text -like 'Copy-Item *Check-Extra.ps1*')){$start=$i;break}}
if($start -lt 0){throw 'Expected corrected export checkpoint absent'}
$tail=($statements[$start..($statements.Count-1)] | ForEach-Object {$_.Extent.Text}) -join "`r`n"
$inputRoot=$PSScriptRoot
$tail=$tail.Replace('$PSScriptRoot','$inputRoot')
if($ResumeRemaining){
 $prior=Get-Content "$root\rehearsals.json" -Raw | ConvertFrom-Json
 $done=@($prior | ForEach-Object Control)
 $results=New-Object 'System.Collections.Generic.List[object]'
 foreach($entry in $prior){if($entry.Protected -ne 'PASS' -or $entry.Planted -ne 'FAIL' -or $entry.Repaired -ne 'PASS' -or $entry.Final -ne 'FAIL'){throw 'Prior control evidence invalid'};$results.Add($entry)}
 foreach($id in $extra | Where-Object {$_ -in $done}){if((Probe $id) -ne 'FAIL'){throw 'Previously planted extra control changed'}}
 $remaining=@($extra | Where-Object {$_ -notin $done})
 if(($remaining -join ',') -ne 'firewall,audit-logon,audit-process,updates,root-trust'){throw 'Unexpected remaining control set'}
 $tail=$tail.Replace('foreach($id in $extra){','foreach($id in $remaining){')
 # Configuration generation must still include all twelve added checks.
 $tail=$tail.Replace('foreach($id in $remaining){$config+=','foreach($id in $extra){$config+=')
}
Copy-Item $PSCommandPath "$root\Resume-Expansion.ps1"
try{Invoke-Expression $tail}catch{$_ | Out-String | Set-Content ("$root\failure-resume-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.txt');throw}
