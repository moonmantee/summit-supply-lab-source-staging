<?php
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$rules=config_get_path('filter/rule', []);
$new=[];
$tracker=time();
foreach ([['opt1','10.77.30.10','10.77.30.1'],['opt2','10.77.70.10','10.77.70.1']] as [$iface,$source,$destination]) {
    if (config_get_path("interfaces/$iface/ipaddr") !== $destination) { throw new Exception('Unexpected mapping'); }
    foreach ([['tcp/udp','53','DNS'],['udp','123','NTP']] as [$protocol,$port,$service]) {
        $description="Lab $source to local $service";
        if (in_array($description, array_column($rules,'descr'))) { continue; }
        $new[]=['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>$protocol,
            'tracker'=>(string)$tracker++,'statetype'=>'keep state',
            'source'=>['address'=>$source], 'destination'=>['address'=>$destination,'port'=>$port], 'descr'=>$description];
    }
}
if (!$new) { echo "No new rules needed\n"; exit; }
$backup='/conf/backup/pre-infra-rules-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
chmod($backup,0600);
config_set_path('filter/rule',array_merge($new,$rules));
write_config('Allow migrated guests to use only their local firewall DNS and NTP services');
echo 'Apply result: ',json_encode(filter_configure_sync()),"\nBackup: $backup\n";
