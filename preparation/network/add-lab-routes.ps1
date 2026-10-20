$ErrorActionPreference = 'Stop'
$administrator = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $administrator.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator, then run this script again.'
}
$labInterface = Get-NetIPAddress -InterfaceAlias 'VMware Network Adapter VMnet2' -AddressFamily IPv4 -IPAddress '10.77.10.50'
foreach ($labSubnet in @('10.77.20.0/24', '10.77.30.0/24', '10.77.40.0/24', '10.77.70.0/24')) {
    $existingRoute = Get-NetRoute -DestinationPrefix $labSubnet -ErrorAction SilentlyContinue
    if ($existingRoute) {
        if ($existingRoute | Where-Object { $_.NextHop -ne '10.77.10.1' -or $_.InterfaceIndex -ne $labInterface.InterfaceIndex }) {
            throw "Conflicting route for $labSubnet; no automatic replacement."
        }
    } else {
        $networkAddress = $labSubnet.Split('/')[0]
        & "$env:SystemRoot\System32\route.exe" -p -4 ADD $networkAddress MASK 255.255.255.0 10.77.10.1 METRIC 5 IF $labInterface.InterfaceIndex
        if ($LASTEXITCODE -ne 0) { throw "Could not add $labSubnet. Exit code: $LASTEXITCODE" }
    }
    $verifiedRoute = Get-NetRoute -DestinationPrefix $labSubnet -ErrorAction Stop | Where-Object { $_.NextHop -eq '10.77.10.1' -and $_.InterfaceIndex -eq $labInterface.InterfaceIndex }
    if (-not $verifiedRoute) { throw "Route verification failed for $labSubnet" }
}
Get-NetRoute -InterfaceIndex $labInterface.InterfaceIndex -AddressFamily IPv4 | Select-Object DestinationPrefix,NextHop
