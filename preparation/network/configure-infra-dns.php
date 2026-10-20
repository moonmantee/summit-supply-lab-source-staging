<?php
require_once('config.inc');
require_once('functions.inc');
require_once('system.inc');
require_once('services.inc');
$backup='/conf/backup/pre-infra-dns-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
chmod($backup,0600);
$hosts=config_get_path('unbound/hosts',[]);
foreach (['range-fw'=>'10.77.10.1','score01'=>'10.77.70.10'] as $name=>$ip) {
    $found=false;
    foreach ($hosts as $entry) {
        if (($entry['host']??'')===$name && ($entry['domain']??'')==='infra.test') {
            if (($entry['ip']??'')!==$ip) { throw new Exception('Conflicting DNS record'); }
            $found=true;
        }
    }
    if (!$found) { $hosts[]=['host'=>$name,'domain'=>'infra.test','ip'=>$ip,'descr'=>'Summit organizer infrastructure']; }
}
config_set_path('system/hostname','range-fw');
config_set_path('unbound/hosts',$hosts);
write_config('Correct range-fw hostname and add infrastructure DNS records');
echo 'Hostname result: ',system_hostname_configure(),"\n";
echo 'Resolver result: ',services_unbound_configure(false),"\nBackup: $backup\n";
