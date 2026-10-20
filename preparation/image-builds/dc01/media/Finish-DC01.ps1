# Complete clean lab DNS/time configuration after successful domain promotion.
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'DC01' -or (Get-ADDomain).DNSRoot -ne 'corp.summit.test') { throw 'Unexpected domain controller' }
$backup = 'C:\ProgramData\SummitLab\post-promotion-before-dns.json'
if (-not (Test-Path $backup)) {
    [pscustomobject]@{
        ClientDNS = @(Get-DnsClientServerAddress -InterfaceAlias Ethernet0)
        Forwarders = Get-DnsServerForwarder
        Zones = @(Get-DnsServerZone)
    } | ConvertTo-Json -Depth 6 | Set-Content $backup
}
Set-DnsClientServerAddress -InterfaceAlias Ethernet0 -ServerAddresses '10.77.40.10'
# Clean-build forwarding through the firewall; no fallback to public root hints.
Set-DnsServerForwarder -IPAddress '10.77.40.1' -UseRootHint $false
foreach ($subnet in @('40','30')) {
    $zone = "$subnet.77.10.in-addr.arpa"
    if (-not (Get-DnsServerZone -Name $zone -ErrorAction SilentlyContinue)) {
        Add-DnsServerPrimaryZone -NetworkId "10.77.$subnet.0/24" -ReplicationScope Domain -DynamicUpdate Secure
    }
}
$shop = @(Get-DnsServerResourceRecord -ZoneName 'corp.summit.test' -Name shop01 -RRType A -ErrorAction SilentlyContinue)
if ($shop.Count -eq 0) {
    Add-DnsServerResourceRecordA -ZoneName 'corp.summit.test' -Name shop01 -IPv4Address '10.77.30.10'
} elseif (@($shop | Where-Object { $_.RecordData.IPv4Address.IPAddressToString -ne '10.77.30.10' }).Count) { throw 'Conflicting shop01 record' }
foreach ($item in @(@('40.77.10.in-addr.arpa','dc01.corp.summit.test.'),@('30.77.10.in-addr.arpa','shop01.corp.summit.test.'))) {
    $ptr = @(Get-DnsServerResourceRecord -ZoneName $item[0] -Name '10' -RRType PTR -ErrorAction SilentlyContinue)
    if ($ptr.Count -eq 0) { Add-DnsServerResourceRecordPtr -ZoneName $item[0] -Name '10' -PtrDomainName $item[1] }
    elseif (@($ptr | Where-Object { $_.RecordData.PtrDomainName -ne $item[1] }).Count) { throw 'Conflicting reverse record' }
}
& w32tm.exe /config /manualpeerlist:'10.77.40.1,0x8' /syncfromflags:manual /reliable:yes /update
if ($LASTEXITCODE -ne 0) { throw 'PDC time configuration failed' }
& w32tm.exe /resync /rediscover
if ($LASTEXITCODE -ne 0) { throw 'PDC time synchronization failed' }
'Post-promotion DNS and time configuration completed.'
