param([string]$Check,[string]$AnswerRoot='C:\Users\Public\Documents\SummitMailCompetition')
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
. "$PSScriptRoot\Answer.ps1"
function Answer-Verdict([string]$Text,[string]$ExpectedHash){
 $answer=Get-AnswerValue $Text
 if($null -eq $answer){return 'ERROR'}
 if($answer -eq ''){return 'FAIL'}
 if((Get-TextHash $answer) -eq $ExpectedHash){return 'PASS'};return 'FAIL'
}
function Invoke-ForensicCheck([string]$Id,[string]$Root='C:\Users\Public\Documents\SummitMailCompetition'){
 try{
  if($env:COMPUTERNAME -ne 'MAIL01' -or $Id -notmatch '^Q0[123]$'){throw 'Wrong target/check'}
  $meta=Get-Content C:\aeacus\probes\forensics.json -Raw|ConvertFrom-Json
  $number=[int]$Id.Substring(1);$record=@($meta.questions|Where-Object id -eq $Id)
  if($record.Count -ne 1){throw 'Question metadata missing'}
  foreach($e in $record[0].evidence){if((Get-FileHash -LiteralPath $e.path).Hash -ne $e.sha256){throw 'Preserved evidence missing or modified'}}
  $path=Join-Path $Root "Forensic Question $number.txt"
  if(-not(Test-Path -LiteralPath $path)){throw 'Answer file absent'}
  return Answer-Verdict ([IO.File]::ReadAllText($path)) $record[0].answerHash
 }catch{return 'ERROR'}
}
if($Check){Invoke-ForensicCheck $Check $AnswerRoot}
