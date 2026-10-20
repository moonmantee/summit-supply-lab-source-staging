$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
foreach($port in @(53,88,389,445)) {
 $client=New-Object Net.Sockets.TcpClient
 try {$pending=$client.ConnectAsync('10.77.40.10',$port);$ok=$pending.Wait(2500) -and $client.Connected;[pscustomobject]@{host='dc01';port=$port;connected=$ok} | ConvertTo-Json -Compress}
 catch {[pscustomobject]@{host='dc01';port=$port;connected=$false} | ConvertTo-Json -Compress}
 finally {$client.Dispose()}
}
'DNS';nslookup -timeout=2 -retry=1 dc01.corp.summit.test 10.77.40.10
'native local auth API'
$code='using System;using System.Runtime.InteropServices;public class LocalSamTest {[DllImport("Netapi32.dll",CharSet=CharSet.Unicode)]public static extern int NetUserGetInfo(string s,string u,int l,out IntPtr p);[DllImport("Netapi32.dll")]public static extern int NetApiBufferFree(IntPtr p);}'
Add-Type $code
$p=[IntPtr]::Zero;$watch=[Diagnostics.Stopwatch]::StartNew();$rc=[LocalSamTest]::NetUserGetInfo($null,'Administrator',0,[ref]$p);$watch.Stop();if($p -ne [IntPtr]::Zero){[LocalSamTest]::NetApiBufferFree($p) | Out-Null}
[pscustomobject]@{returnCode=$rc;elapsedMs=$watch.ElapsedMilliseconds} | ConvertTo-Json -Compress
