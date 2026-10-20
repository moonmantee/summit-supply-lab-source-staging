$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($env:COMPUTERNAME -ne 'MAIL01'){throw 'Wrong guest'}
$root=(Get-Content C:\ProgramData\SummitLab\MailCompetition-current.txt -Raw).Trim()
$status=Get-Content "$root\status.json" -Raw|ConvertFrom-Json
if($status.phase -ne 'runtime-verified'){throw 'Production scoring not verified'}
$meta=Get-Content "$root\metadata.json" -Raw|ConvertFrom-Json
$matrix=@(Get-Content "$root\matrix.jsonl"|ForEach-Object {$_|ConvertFrom-Json})
$targets=@{U01='MAIL01\mail.contractor';U02='MAIL01\mail.audit administrative membership';S01='SSH PermitEmptyPasswords';S02='SSH forwarding';S03='SSH LoginGraceTime';W01='MailEnable WebMail directoryBrowse';W02='MailEnable WebMail httpErrors';W03='MailEnable WebMail TRACE request filtering';W04='MailEnable WebMail request-size limit';L01='Process Creation auditing';L02='User Account Management auditing';L03='Failed Logon auditing';P01='Interactive logon notice';P02='Machine inactivity limit';P03='Anonymous SAM enumeration';A01='SummitMailScenario\operations.ps1';A02='SummitMailScenario\Maintenance';A03='SummitMailScenario\confidential.txt';A04='SummitMailScenario\test_authorized_keys';M01='\SummitMailScenario\MailboxCacheSync';M02='HKLM Run\SummitMailLegacy';D01='SummitMail-UnnecessaryIngress';O01='Windows Update NoAutoUpdate';F01='Operations fictional credentials';F02='Operations synthetic media archive'}
$weak=@{U01='Synthetic interactive account enabled';U02='Synthetic employee granted local administrator';S01='yes; no usable blank-password account created';S02='DisableForwarding no, forwarding otherwise allowed';S03='600 seconds';W01='enabled';W02='Detailed remote errors';W03='TRACE explicitly allowed';W04='2147483647 bytes';L01='Success disabled';L02='Success disabled';L03='Failure disabled';P01='Caption and text blank';P02='0 seconds';P03='RestrictAnonymousSAM 0';A01='Ordinary users full control';A02='Ordinary users may create executables';A03='Ordinary users may read confidential fixture';A04='Ordinary users may modify inert key fixture';M01='Inert LocalService scheduled activation enabled';M02='Inert startup activation present';D01='Unnecessary TCP 9999 ingress allowed';O01='NoAutoUpdate 1';F01='Identified fictional content present in Operations';F02='Identified synthetic archive present in Operations'}
foreach($issue in $meta.issueManifest){
 $evidence=@($matrix|Where-Object id -eq $issue.id)
 if($evidence.Count -ne 4 -or @($evidence|Where-Object {($_.state -in @('protected','repaired') -and $_.verdict -ne 'PASS') -or ($_.state -in @('planted','final-planted') -and $_.verdict -ne 'FAIL')}).Count){throw 'Incomplete issue rehearsal evidence'}
 $fields=@{target=$targets[$issue.id];planted_state=$weak[$issue.id];repair=$issue.policy;dependencies=@('Windows PowerShell 5.1','Required native target component and preserved business fixture','C:\aeacus\probes\Probe.ps1');evidence=$evidence;evidenceProbeHash=$status.probeHash;evidenceConfigHash=$status.configHash;status='runtime-verified'}
 foreach($k in $fields.Keys){$issue|Add-Member -NotePropertyName $k -NotePropertyValue $fields[$k] -Force}
}
$extra=@{status='runtime-verified';actualOS='Windows Server 2022 Datacenter build 20348';mailVersion='MailEnable 10.59';domain='corp.summit.test';expectedRestored=0;manualAcceptance='pending';export='not-performed';defenderApprovedExclusion='C:\aeacus\phocus.exe';probeHash=$status.probeHash;configHash=$status.configHash;preservation=$status.preservation}
foreach($k in $extra.Keys){$meta|Add-Member -NotePropertyName $k -NotePropertyValue $extra[$k] -Force}
$meta|ConvertTo-Json -Depth 12|Set-Content "$root\metadata.json" -Encoding UTF8
$target='C:\aeacus\probes\metadata.json';$temp='C:\aeacus\probes\metadata-'+[guid]::NewGuid().ToString('N')+'.tmp'
Copy-Item "$root\metadata.json" $temp
$backup="$root\backup\pre-final-metadata-$([guid]::NewGuid().ToString('N')).json"
[IO.File]::Replace($temp,$target,$backup)
[ordered]@{machine='MAIL01';issueCount=25;points=100;manifestStatus='runtime-verified';metadataHash=(Get-FileHash $target).Hash;probeHash=$status.probeHash;configHash=$status.configHash}|ConvertTo-Json
