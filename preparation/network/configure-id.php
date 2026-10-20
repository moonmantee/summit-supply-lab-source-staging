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
if (isset($interfaces['opt3']) && ($interfaces['opt3']['if'] ?? '') !== 'em4') { throw new Exception('opt3 already assigned elsewhere'); }
foreach ($interfaces as $name => $value) {
    if ($name !== 'opt3' && ($value['if'] ?? '') === 'em4') { throw new Exception('em4 already assigned'); }
}
$backup = '/conf/backup/pre-ID-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml', $backup)) { throw new Exception('Backup failed'); }
chmod($backup, 0600);
config_set_path('interfaces/opt3', ['if'=>'em4','descr'=>'ID','enable'=>'','ipaddr'=>'10.77.40.1','subnet'=>'24']);
$rules = config_get_path('filter/rule', []);
$planned = [
 ['lan','10.77.10.50','10.77.40.10','tcp','22','Organizer SSH to dc01'],
 ['opt3','10.77.40.10','10.77.40.1','tcp/udp','53','Lab dc01 to local DNS'],
 ['opt3','10.77.40.10','10.77.40.1','udp','123','Lab dc01 to local NTP'],
];
$tracker = time();
foreach ($planned as [$iface,$source,$destination,$protocol,$port,$description]) {
    if (in_array($description,array_column($rules,'descr'))) { continue; }
    while (in_array((string)$tracker,array_column($rules,'tracker'))) { $tracker++; }
    array_unshift($rules,['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>$protocol,
      'tracker'=>(string)$tracker++,'statetype'=>'keep state','source'=>['address'=>$source],
      'destination'=>['address'=>$destination,'port'=>$port],'descr'=>$description]);
}
config_set_path('filter/rule',$rules);
write_config('Add isolated CCDC-ID interface and scoped dc01 infrastructure access');
interface_configure('opt3');
services_unbound_configure(false);
system_ntp_configure();
echo 'Filter result: ',json_encode(filter_configure_sync()),"\nBackup: $backup\n";
echo json_encode(config_get_path('interfaces/opt3')), "\n";
