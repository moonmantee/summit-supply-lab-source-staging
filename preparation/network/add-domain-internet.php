<?php
require_once('config.inc');
require_once('functions.inc');
require_once('interfaces.inc');
require_once('filter.inc');
require_once('shaper.inc');
$hosts = [
 ['workstation01','opt4','10.77.20.10','10.77.20.1'],
 ['shop01','opt1','10.77.30.10','10.77.30.1'],
 ['forum01','opt1','10.77.30.20','10.77.30.1'],
 ['mail01','opt1','10.77.30.30','10.77.30.1'],
 ['sql01','opt5','10.77.50.20','10.77.50.1'],
 ['dc01','opt3','10.77.40.10','10.77.40.1'],
 ['score01','opt2','10.77.70.10','10.77.70.1'],
];
$interfaces = config_get_path('interfaces', []);
foreach ($hosts as [$name,$iface,$ip,$gateway]) {
 if (($interfaces[$iface]['ipaddr'] ?? '') !== $gateway) { throw new Exception('Unexpected interface for '.$name); }
}
if (config_get_path('nat/outbound/mode') !== 'automatic') { throw new Exception('Review outbound NAT mode before applying'); }
$rules = config_get_path('filter/rule', []);
$added = [];
$tracker = time();
$add = function($iface,$ip,$destination,$protocol,$port,$description) use (&$rules,&$added,&$tracker) {
 $dest = $destination;
 $dest['port'] = $port;
 foreach (array_merge($rules,$added) as $r) {
  if (isset($r['disabled']) || ($r['type'] ?? '') !== 'pass' || ($r['interface'] ?? '') !== $iface || ($r['ipprotocol'] ?? '') !== 'inet') { continue; }
  if (($r['source'] ?? []) === ['address'=>$ip] && ($r['destination'] ?? []) === $dest && in_array($r['protocol'] ?? '', [$protocol,'tcp/udp'], true)) { return; }
  if (($r['descr'] ?? '') === $description) { throw new Exception('Conflicting managed rule: '.$description); }
 }
 while (in_array((string)$tracker,array_column(array_merge($rules,$added),'tracker'))) { $tracker++; }
 $added[] = ['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>$protocol,'tracker'=>(string)$tracker++,'statetype'=>'keep state','source'=>['address'=>$ip],'destination'=>$dest,'descr'=>$description];
};
foreach ($hosts as [$name,$iface,$ip,$gateway]) {
 if (!in_array($name,['dc01','score01'],true)) {
  foreach (['tcp'=>['53','88','135','389','445','464','636','3268','3269','49152-65535'], 'udp'=>['53','88','123','389','464']] as $protocol=>$ports) {
   foreach ($ports as $port) { $add($iface,$ip,['address'=>'10.77.40.10'],$protocol,$port,'CCDC '.$name.' domain '.$protocol.' '.$port); }
  }
 }
 foreach (['80','443'] as $port) { $add($iface,$ip,['address'=>'CCDC_NONINTERNET_V4','not'=>''],'tcp',$port,'CCDC '.$name.' internet TCP '.$port); }
}
$alias = ['name'=>'CCDC_NONINTERNET_V4','type'=>'network','address'=>'0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 240.0.0.0/4','descr'=>'Exclude local, private, shared, multicast and reserved destinations from web egress'];
$aliases = config_get_path('aliases/alias', []);
$found = false;
foreach ($aliases as $existing) {
 if (($existing['name'] ?? '') === $alias['name']) {
  if (($existing['type'] ?? '') !== $alias['type'] || ($existing['address'] ?? '') !== $alias['address']) { throw new Exception('Conflicting egress alias'); }
  $found = true;
 }
}
echo json_encode(['new_rules'=>count($added),'nat_mode'=>'automatic','alias'=>$alias,'rules'=>$added], JSON_PRETTY_PRINT),"\n";
if (($argv[1] ?? '') !== '--apply') { exit(0); }
$backup = '/conf/backup/pre-domain-internet-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
chmod($backup,0600);
if (!$found) { $aliases[] = $alias; config_set_path('aliases/alias',$aliases); }
config_set_path('filter/rule',array_merge($added,$rules));
write_config('Add scoped CCDC domain connectivity and public HTTP/HTTPS egress for lab hosts');
alias_make_table();
$result = filter_configure_sync();
echo 'Filter result: ',json_encode($result),"\nBackup: $backup\n";
