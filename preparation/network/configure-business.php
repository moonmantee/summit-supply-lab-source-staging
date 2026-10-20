<?php
require_once('config.inc');
require_once('functions.inc');
require_once('interfaces.inc');
require_once('filter.inc');
require_once('shaper.inc');
require_once('services.inc');
require_once('system.inc');
$interfaces = config_get_path('interfaces', []);
if (($interfaces['lan']['ipaddr'] ?? '') !== '10.77.10.1') { throw new Exception('Unexpected management interface'); }
if (isset($interfaces['opt4']) && ($interfaces['opt4']['if'] ?? '') !== 'em5') { throw new Exception('opt4 already assigned elsewhere'); }
foreach ($interfaces as $name => $value) {
    if ($name !== 'opt4' && ($value['if'] ?? '') === 'em5') { throw new Exception('em5 already assigned'); }
}
$backup = '/conf/backup/pre-BUSINESS-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml', $backup)) { throw new Exception('Backup failed'); }
chmod($backup, 0600);
config_set_path('interfaces/opt4', ['if'=>'em5','descr'=>'BUSINESS','enable'=>'','ipaddr'=>'10.77.20.1','subnet'=>'24']);
$rules = config_get_path('filter/rule', []);
$planned = [
 ['lan','10.77.10.50','10.77.20.10','tcp','22','Organizer SSH to workstation01'],
 ['opt4','10.77.20.10','10.77.20.1','udp','123','Workstation bootstrap time'],
 ['opt4','10.77.20.10','10.77.30.10','tcp','443','Workstation shop HTTPS'],
];
foreach (['53','88','135','389','445','464','636','3268','3269','49152-65535'] as $port) {
 $planned[]=['opt4','10.77.20.10','10.77.40.10','tcp',$port,'Workstation AD TCP '.$port];
}
foreach (['53','88','123','389','464'] as $port) {
 $planned[]=['opt4','10.77.20.10','10.77.40.10','udp',$port,'Workstation AD UDP '.$port];
}
$tracker = time();
foreach ($planned as [$iface,$source,$destination,$protocol,$port,$description]) {
    if (in_array($description,array_column($rules,'descr'))) { continue; }
    while (in_array((string)$tracker,array_column($rules,'tracker'))) { $tracker++; }
    array_unshift($rules,['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>$protocol,
      'tracker'=>(string)$tracker++,'statetype'=>'keep state','source'=>['address'=>$source],
      'destination'=>['address'=>$destination,'port'=>$port],'descr'=>$description]);
}
config_set_path('filter/rule',$rules);
write_config('Add BUSINESS interface and scoped workstation AD access');
interface_configure('opt4');
services_unbound_configure(false);
system_ntp_configure();
echo 'Filter result: ',json_encode(filter_configure_sync()),"\nBackup: $backup\n";
echo json_encode(config_get_path('interfaces/opt4')), "\n";

