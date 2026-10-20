# Run locally on dc01 in elevated PowerShell after clean network validation.
# The DSRM recovery password is prompted by Windows and never stored in this script.
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'DC01') { throw 'Run only on dc01.' }
if ((Get-CimInstance Win32_ComputerSystem).PartOfDomain) { throw 'Already domain joined; inspect before continuing.' }
if (-not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress '10.77.40.10' -ErrorAction SilentlyContinue)) { throw 'Complete ID network migration first.' }
if ((Get-WindowsFeature AD-Domain-Services).InstallState -ne 'Installed') { throw 'Install and verify AD DS first.' }
Import-Module ADDSDeployment
# Omitting SafeModeAdministratorPassword invokes the native secure confirmation prompt.
# The standard prerequisite checks remain enabled and successful promotion reboots.
Install-ADDSForest -DomainName 'corp.summit.test' -DomainNetbiosName 'CORP' -ForestMode WinThreshold -DomainMode WinThreshold -InstallDns -CreateDnsDelegation:$false -Force
