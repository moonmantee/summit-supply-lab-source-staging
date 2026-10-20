$ErrorActionPreference='Stop'
if(-not(Test-Path "$PSScriptRoot\Forensic.ps1")){throw 'Forensic scorer is missing'}
. "$PSScriptRoot\Forensic.ps1"
$hash=Get-TextHash 'mail01\mail.audit'
if((Answer-Verdict "Question: mail01\mail.audit`nAnswer:`n" $hash) -ne 'FAIL'){throw 'Question text must not award points'}
if((Answer-Verdict "Answer:`nwrong" $hash) -ne 'FAIL'){throw 'Wrong answer must fail'}
if((Answer-Verdict "Answer:`n  MAIL01\MAIL.AUDIT  `r`n" $hash) -ne 'PASS'){throw 'Correct normalized answer must pass'}
if((Answer-Verdict "Answer:`nwrong`nAnswer:`nmail01\mail.audit" $hash) -ne 'ERROR'){throw 'Ambiguous sections must error'}
if((Answer-Verdict "No answer section" $hash) -ne 'ERROR'){throw 'Malformed file must error'}
'PASS: answer-only scoring, wrong/blank/correct and malformed regressions'
