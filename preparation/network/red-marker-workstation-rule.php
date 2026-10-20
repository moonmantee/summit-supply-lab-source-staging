<?php
// Single callback exception for the harmless workstation01 marker rehearsal.
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$interfaces = config_get_path('interfaces', []);
if (($interfaces['opt4']['ipaddr'] ?? '') !== '10.77.20.1' ||
    ($interfaces['opt2']['ipaddr'] ?? '') !== '10.77.70.1') {
    throw new Exception('Unexpected lab interfaces');
}
$desired = ['type'=>'pass','interface'=>'opt4','ipprotocol'=>'inet','protocol'=>'tcp',
    'source'=>['address'=>'10.77.20.10'],
    'destination'=>['address'=>'10.77.70.10','port'=>'8770']];
$description = 'RED-MARKER workstation01 callback TLS';
$rules = config_get_path('filter/rule', []);
foreach ($rules as $rule) {
    if (($rule['descr'] ?? '') !== $description) { continue; }
    foreach ($desired as $k=>$v) {
        if (($rule[$k] ?? null) !== $v || isset($rule['disabled'])) {
            throw new Exception('Conflicting existing marker rule');
        }
    }
    echo "Exact marker rule already exists\n";
    exit(0);
}
echo json_encode(['new_rule'=>$desired], JSON_PRETTY_PRINT), "\n";
if (($argv[1] ?? '') !== '--apply') { exit(0); }
$backup = '/conf/backup/pre-RED-MARKER-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml', $backup)) { throw new Exception('Backup failed'); }
chmod($backup, 0600);
$tracker = time();
while (in_array((string)$tracker, array_column($rules, 'tracker'))) { $tracker++; }
$rule = array_merge($desired, ['tracker'=>(string)$tracker, 'statetype'=>'keep state', 'descr'=>$description]);
config_set_path('filter/rule', array_merge([$rule], $rules));
write_config('Allow only workstation01 marker exercise TLS callback; preserve SCORE protections');
$result = filter_configure_sync();
echo json_encode(['backup'=>$backup,'filter_result'=>$result]), "\n";
