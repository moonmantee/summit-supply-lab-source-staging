$ErrorActionPreference='Stop'
if(-not(Test-Path "$PSScriptRoot\Probe.ps1")){throw 'Expected mail probe implementation missing'}
. "$PSScriptRoot\Probe.ps1"
if((Verdict $true) -ne 'PASS' -or (Verdict $false) -ne 'FAIL' -or (Verdict $null) -ne 'ERROR'){throw 'Tri-state contract failed'}
if(-not (Test-ScenarioAcl 'O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;BU)' 'ReadOnly')){throw 'Ordinary read must work'}
if(Test-ScenarioAcl 'O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FW;;;BU)' 'ReadOnly'){throw 'Ordinary write must fail'}
if(Test-ScenarioAcl 'O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)' 'ReadOnly'){throw 'Everyone full control must fail'}
if(Test-ScenarioAcl 'O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;BU)' 'Private'){throw 'Ordinary confidential read must fail'}
if(Test-ScenarioAcl 'O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)' 'ReadOnly'){throw 'Deleting ordinary read must fail'}
if(Test-ScenarioAcl 'O:SYG:SYD:P(D;;FR;;;BU)(A;;FA;;;SY)(A;;FA;;;BA)(A;;FRFX;;;BU)' 'ReadOnly'){throw 'Denying ordinary read must fail'}
if(@(Get-ControlIds).Count -ne 25 -or @((Get-ControlIds)|Select-Object -Unique).Count -ne 25){throw 'Expected exactly 25 distinct weaknesses'}
if((Invoke-MailCheck 'INVALID') -ne 'ERROR'){throw 'Invalid control must error'}
'PASS: tri-state, ACL regressions, count and invalid-control tests'
