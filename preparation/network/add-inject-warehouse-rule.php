<?php
// White Team infrastructure prerequisite: score01 -> warehouse task endpoint only.
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
if (config_get_path('interfaces/opt2/ipaddr') !== '10.77.70.1' ||
    config_get_path('interfaces/opt4/ipaddr') !== '10.77.20.1') {
    throw new Exception('Unexpected SCORE or workstation interface');
}
$rules = config_get_path('filter/rule', []);
$desired = ['type'=>'pass','interface'=>'opt2','ipprotocol'=>'inet','protocol'=>'tcp',
    'source'=>['address'=>'10.77.70.10'],
    'destination'=>['address'=>'10.77.20.10','port'=>'8080']];
foreach ($rules as $rule) {
    $same = !isset($rule['disabled']);
    foreach ($desired as $key=>$value) { if (($rule[$key] ?? null) !== $value) { $same = false; } }
    if ($same) { echo "Exact warehouse scoring rule already present.\n"; exit(0); }
}
$tracker=time();
while (in_array((string)$tracker,array_column($rules,'tracker'))) { $tracker++; }
$rule=array_merge($desired,['tracker'=>(string)$tracker,'statetype'=>'keep state','descr'=>'Scorer workstation01 warehouse HTTP after I06']);
echo json_encode($rule,JSON_PRETTY_PRINT),"\n";
if (($argv[1] ?? '') !== '--apply') { exit(0); }
$backup='/conf/backup/pre-INJECT-WAREHOUSE-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
chmod($backup,0600);
config_set_path('filter/rule',array_merge([$rule],$rules));
write_config('Allow score01 to grade I06 warehouse HTTP endpoint only');
$result=filter_configure_sync();
echo 'Filter result: ',json_encode($result),"\nBackup: $backup\n";
