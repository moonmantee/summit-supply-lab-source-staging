$ErrorActionPreference='Stop'
if(-not(Test-Path "$PSScriptRoot\Probe.ps1")){throw 'FAIL: tri-state native probe is missing'}
. "$PSScriptRoot\Probe.ps1"
if((Get-IisValue 'Custom') -ne 'Custom'){throw 'IIS scalar enum must remain observable'}
if((Get-IisValue ([pscustomobject]@{Value=$true})) -ne $true){throw 'IIS wrapped Boolean must be unwrapped'}
if((Get-ForumVerdict $true) -ne 'PASS'){throw 'Protected state must pass'}
if((Get-ForumVerdict $false) -ne 'FAIL'){throw 'Observable weak state must fail'}
if((Get-ForumVerdict $null) -ne 'ERROR'){throw 'Missing observation must be an error'}
if((Test-ConfigAcl 'O:SYG:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;BU)(A;;FR;;;IS)') -ne $true){throw 'Read-only users and IIS must be permitted'}
if((Test-ConfigAcl 'O:SYG:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;FW;;;BU)(A;;FR;;;IS)') -ne $false){throw 'User-writable application secrets must fail'}
if((Test-ConfigAcl 'O:SYG:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;FW;;;IS)') -ne $false){throw 'IIS-writable secrets must fail'}
if((Test-ConfigAcl 'O:SYG:SYD:(A;;FA;;;SY)(A;;FA;;;BA)') -ne $false){throw 'Removing application read access must not earn credit'}
if((Test-ConfigAcl 'O:SYG:SYD:(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;IS)') -ne $false){throw 'Removing ordinary-user read access must not earn credit'}
if((Test-ConfigAcl 'O:SYG:SYD:(D;;FR;;;IS)(A;;FA;;;SY)(A;;FA;;;BA)(A;;FR;;;IS)(A;;FR;;;BU)') -ne $false){throw 'Explicit IIS read denial must not earn credit'}
'PASS: probe verdict and secret-file ACL checks'
