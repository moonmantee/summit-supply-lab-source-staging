$ErrorActionPreference='Stop'
$checks=@()
foreach($port in @(53,88,135,389,445,464,3268)) {
 $c=[Net.Sockets.TcpClient]::new()
 try { $task=$c.ConnectAsync('10.77.40.10',$port); if(-not $task.Wait(3000)) {throw 'timeout'}; $checks+=@{target='dc01';port=$port;result='PASS'} }
 catch {$checks+=@{target='dc01';port=$port;result='FAIL';error=$_.Exception.Message}}
 finally {$c.Dispose()}
}
foreach($port in @(8080,8771,8772)) {
 $c=[Net.Sockets.TcpClient]::new()
 try {$task=$c.ConnectAsync('10.77.70.10',$port); if(-not $task.Wait(3000)){throw 'timeout'}; $checks+=@{target='score01';port=$port;result='PASS'}}
 catch {$checks+=@{target='score01';port=$port;result='FAIL';error=$_.Exception.Message}}
 finally {$c.Dispose()}
}
try {$r=Resolve-DnsName -Name '_ldap._tcp.dc._msdcs.corp.summit.test' -Type SRV -Server 10.77.40.10 -DnsOnly; $checks+=@{target='AD SRV';result='PASS';records=@($r).Count}} catch {$checks+=@{target='AD SRV';result='FAIL';error=$_.Exception.Message}}
foreach($url in @('https://example.com','http://10.77.70.10:8080/portal/')) {
 try {$r=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10 -Proxy $null; $checks+=@{target=$url;result='PASS';status=$r.StatusCode}} catch {$checks+=@{target=$url;result='FAIL';error=$_.Exception.Message}}
}
@{host=$env:COMPUTERNAME;checks=$checks} | ConvertTo-Json -Depth 5
