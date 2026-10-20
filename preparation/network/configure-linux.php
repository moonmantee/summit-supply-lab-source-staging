<?php
require_once('config.inc');
require_once('functions.inc');
require_once('interfaces.inc');
require_once('filter.inc');
require_once('shaper.inc');
require_once('services.inc');
require_once('system.inc');
$interfaces = config_get_path('interfaces', []);
foreach (['lan'=>['em1','10.77.10.1'], 'opt1'=>['em2','10.77.30.1'], 'opt2'=>['em3','10.77.70.1'], 'opt3'=>['em4','10.77.40.1'], 'opt4'=>['em5','10.77.20.1']] as $name=>$expected) {
    if (($interfaces[$name]['if'] ?? '') !== $expected[0] || ($interfaces[$name]['ipaddr'] ?? '') !== $expected[1]) { throw new Exception('Unexpected interface: '.$name); }
}
if (isset($interfaces['opt5']) && (($interfaces['opt5']['if'] ?? '') !== 'em6' || ($interfaces['opt5']['ipaddr'] ?? '') !== '10.77.50.1')) { throw new Exception('opt5 already assigned elsewhere'); }
foreach ($interfaces as $name=>$value) {
    if ($name !== 'opt5' && ($value['if'] ?? '') === 'em6') { throw new Exception('em6 already assigned'); }
}
$planned = [
 ['lan','10.77.10.50','10.77.50.20','tcp','22','Organizer SSH to sql01'],
 ['opt5','10.77.50.20','10.77.50.1','udp','123','sql01 lab time'],
 ['opt1','10.77.30.10','10.77.50.20','tcp','3306','shop01 database on sql01'],
 ['opt1','10.77.30.20','10.77.50.20','tcp','3306','forum01 database on sql01'],
 ['opt2','10.77.70.10','10.77.50.20','tcp','3306','Scorer SQL transactions'],
 ['opt4','10.77.20.10','10.77.50.20','tcp','3306','Business SQL reporting'],
 ['opt4','10.77.20.10','10.77.50.20','tcp','22','Business SQL administration'],
];
foreach (['53','88','389','445','464','3268'] as $port) {
    $planned[]=['opt5','10.77.50.20','10.77.40.10','tcp',$port,'sql01 AD TCP '.$port];
}
foreach (['53','88','389','464'] as $port) {
    $planned[]=['opt5','10.77.50.20','10.77.40.10','udp',$port,'sql01 AD UDP '.$port];
}
$rules = config_get_path('filter/rule', []);
$tracker = time();
$added = [];
foreach ($planned as [$iface,$source,$destination,$protocol,$port,$description]) {
    $matches = array_values(array_filter($rules, fn($r)=>($r['descr'] ?? '') === $description));
    if ($matches) {
        if (count($matches) !== 1) { throw new Exception('Duplicate rule: '.$description); }
        $r=$matches[0];
        if (isset($r['disabled']) || ($r['type'] ?? '') !== 'pass' || ($r['interface'] ?? '') !== $iface || ($r['ipprotocol'] ?? '') !== 'inet' || ($r['protocol'] ?? '') !== $protocol || ($r['source'] ?? []) !== ['address'=>$source] || ($r['destination'] ?? []) !== ['address'=>$destination,'port'=>$port]) { throw new Exception('Conflicting rule: '.$description); }
        continue;
    }
    while (in_array((string)$tracker,array_column(array_merge($rules,$added),'tracker'))) { $tracker++; }
    $added[]=['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>$protocol,'tracker'=>(string)$tracker++,'statetype'=>'keep state','source'=>['address'=>$source],'destination'=>['address'=>$destination,'port'=>$port],'descr'=>$description];
}
echo json_encode(['interface'=>['opt5','em6','10.77.50.1/24'],'new_rules'=>$added],JSON_PRETTY_PRINT),"\n";
if (($argv[1] ?? '') !== '--apply') { exit(0); }
exec('/sbin/ifconfig em6', $output, $status);
if ($status !== 0) { throw new Exception('em6 is not available'); }
$backup='/conf/backup/pre-LINUX-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
chmod($backup,0600);
config_set_path('interfaces/opt5',['if'=>'em6','descr'=>'LINUX','enable'=>'','ipaddr'=>'10.77.50.1','subnet'=>'24']);
config_set_path('filter/rule',array_merge($added,$rules));
write_config('Add isolated LINUX network and scoped sql01 business/domain access');
interface_configure('opt5');
system_ntp_configure();
echo 'Filter result: ',json_encode(filter_configure_sync()),"\nBackup: $backup\n";
