$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
foreach($p in @('C:\aeacus\scoring.conf','C:\aeacus\scoring.dat','C:\aeacus\assets\ScoringReport.html')){if(Test-Path $p){throw "Existing scorer artifact requires reviewed cutover: $p"}}
if(Get-Service CSSClient -ErrorAction SilentlyContinue){throw 'Existing scorer service'}
if((Get-FileHash C:\aeacus\phocus.exe).Hash -ne 'BF266B0E2BFCCB6AA871D61D2D9584ACBB2B11D19D5598E4435C78294A57DD4A'){throw 'Pinned runtime hash mismatch'}
$record='C:\ProgramData\SummitLab\MailRuntimePreflight-'+[guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $record|Out-Null
& icacls.exe $record /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F'|Out-Null
if($LASTEXITCODE){throw 'Private ACL failed'}
$config=@('name = "mail01-preflight"','title = "MAIL01 runtime compatibility"','os = "Windows Server 2022"','user = "Administrator"','version = "2.1.1"','local = true','shell = false')
1..25|ForEach-Object {$config+=@('[[check]]',('message = "Compatibility '+$_+'"'),'points = 4','[[check.pass]]',"type = 'CommandOutput'","cmd = 'Write-Output FAIL'","value = 'PASS'")}
$config|Set-Content C:\aeacus\scoring.conf -Encoding ASCII
Copy-Item C:\aeacus\scoring.conf "$record\candidate.conf"
Push-Location C:\aeacus
$success=$false
try{
 & .\aeacus.exe check|Out-Null;if($LASTEXITCODE){throw 'Candidate validation failed'}
 & .\aeacus.exe encrypt|Out-Null;if($LASTEXITCODE -or -not(Test-Path .\scoring.dat)){throw 'Candidate encryption failed'}
 Remove-Item -LiteralPath C:\aeacus\scoring.conf
 $started=[DateTime]::UtcNow
 New-Service CSSClient -BinaryPathName 'C:\aeacus\phocus.exe' -DisplayName 'MAIL01 encrypted scoring compatibility test' -StartupType Manual|Out-Null
 Start-Service CSSClient
 $deadline=(Get-Date).AddSeconds(100)
 do{
  Start-Sleep -Seconds 2
  if((Get-Service CSSClient).Status -ne 'Running'){throw 'Encrypted candidate service stopped'}
  $fresh=$false
  if(Test-Path .\assets\ScoringReport.html){$file=Get-Item .\assets\ScoringReport.html;$html=Get-Content $file.FullName -Raw;$fresh=($file.LastWriteTimeUtc -ge $started -and $html -match '(?<!\d)0 out of 100 points received' -and $html -match '</html>')}
 }until($fresh -or (Get-Date) -gt $deadline)
 if(-not$fresh){throw 'Fresh complete encrypted candidate report missing'}
 Copy-Item .\assets\ScoringReport.html "$record\candidate-report.html"
 $success=$true
}catch{
 $_|Out-String|Set-Content "$record\error.txt"
 Get-MpThreatDetection|Select-Object InitialDetectionTime,ThreatID,ActionSuccess,Resources|ConvertTo-Json -Depth 5|Set-Content "$record\defender-detection.json"
 throw
}finally{
 Pop-Location
 $svc=Get-Service CSSClient -ErrorAction SilentlyContinue
 if($svc){if($svc.Status -ne 'Stopped'){Stop-Service CSSClient};& sc.exe delete CSSClient|Out-Null;if($LASTEXITCODE){throw 'Candidate service removal failed'}}
 foreach($p in @('C:\aeacus\scoring.conf','C:\aeacus\scoring.dat','C:\aeacus\assets\ScoringReport.html')){if(Test-Path $p){Remove-Item -LiteralPath $p}}
 [ordered]@{machine='MAIL01';passed=$success;record=$record;utc=[DateTime]::UtcNow.ToString('o');weaknessesPlanted=$false}|ConvertTo-Json|Set-Content "$record\receipt.json"
}
Get-Content "$record\receipt.json"
