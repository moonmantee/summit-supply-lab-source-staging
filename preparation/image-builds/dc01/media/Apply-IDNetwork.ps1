# Runs once as SYSTEM at startup, after moving the VM's existing adapter to CCDC-ID.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Start-Transcript -Path 'C:\ProgramData\SummitLab\network-migration.log' -Append
try {
    if ($env:COMPUTERNAME -ne 'DC01') { throw 'Unexpected computer' }
    $adapter = @(Get-NetAdapter | Where-Object MacAddress -eq '00-0C-29-BD-9F-F7')
    if ($adapter.Count -ne 1) { throw 'Expected exactly one known adapter' }
    $index = $adapter[0].ifIndex
    Set-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -Dhcp Disabled
    Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object IPAddress -ne '10.77.40.10' | Remove-NetIPAddress -Confirm:$false
    Get-NetRoute -InterfaceIndex $index -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Where-Object NextHop -ne '10.77.40.1' | Remove-NetRoute -Confirm:$false
    if (-not (Get-NetIPAddress -InterfaceIndex $index -IPAddress '10.77.40.10' -ErrorAction SilentlyContinue)) {
        New-NetIPAddress -InterfaceIndex $index -IPAddress '10.77.40.10' -PrefixLength 24 -DefaultGateway '10.77.40.1' | Out-Null
    }
    Set-DnsClientServerAddress -InterfaceIndex $index -ServerAddresses '10.77.40.1'
    # Permit the organizer directly or via its authenticated pfSense SSH jump host.
    Set-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -RemoteAddress '10.77.10.50','10.77.40.1'
    & w32tm.exe /config /manualpeerlist:'10.77.40.1,0x8' /syncfromflags:manual /update
    if ($LASTEXITCODE -ne 0) { throw 'Time configuration failed' }
    'ID network applied' | Set-Content 'C:\ProgramData\SummitLab\network-ready.txt'
    Unregister-ScheduledTask -TaskName 'Summit-Apply-IDNetwork' -Confirm:$false
} finally { Stop-Transcript }
