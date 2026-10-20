$ErrorActionPreference='Stop'
$module=Join-Path $PSScriptRoot 'Answer.ps1'
if(-not(Test-Path $module)){throw 'FAIL: answer parser is missing'}
. $module
foreach($test in @(
 @{text="Question: who?`nEvidence: expected`nAnswer:`n";expected=''},
 @{text="Question: wrong`nAnswer:`n  DOMAIN\User  `r`n";expected='domain\user'},
 @{text="Question: answer exists here only";expected=$null},
 @{text="Answer:`nfirst`nAnswer:`nsecond";expected=$null},
 @{text="Question:`nAnswer:`nABCDEF";expected='abcdef'}
)) {
 $actual=Get-AnswerValue $test.text
 if($actual -cne $test.expected){throw "FAIL: unexpected answer extraction"}
}
'PASS: answer extraction ignores questions and rejects ambiguous sections'
