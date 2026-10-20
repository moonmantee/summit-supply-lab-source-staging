<?php
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');

$interfaces = config_get_path('interfaces', []);
foreach (['lan'=>['em1','10.77.10.1'], 'opt1'=>['em2','10.77.30.1'], 'opt2'=>['em3','10.77.70.1']] as $name=>$expected) {
    if (($interfaces[$name]['if'] ?? '') !== $expected[0] || ($interfaces[$name]['ipaddr'] ?? '') !== $expected[1]) {
        throw new Exception('Unexpected interface mapping: '.$name);
    }
}
$rules = config_get_path('filter/rule', []);
$planned = [
    ['10.77.30.10', '22', 'Organizer SSH to shop01'],
    ['10.77.70.10', '22', 'Organizer SSH to score01'],
    ['10.77.30.10', '443', 'Organizer HTTPS to shop01'],
];
$added = [];
$trackers = array_column($rules, 'tracker');
$tracker = time();
foreach ($planned as [$destination, $port, $description]) {
    $exists = false;
    foreach ($rules as $rule) {
        if (!isset($rule['disabled']) && ($rule['interface'] ?? '') === 'lan' &&
            ($rule['type'] ?? '') === 'pass' && ($rule['ipprotocol'] ?? '') === 'inet' &&
            ($rule['protocol'] ?? '') === 'tcp' && ($rule['source']['address'] ?? '') === '10.77.10.50' &&
            ($rule['destination']['address'] ?? '') === $destination && ($rule['destination']['port'] ?? '') === $port &&
            !isset($rule['source']['not']) && !isset($rule['destination']['not']) && !isset($rule['source']['port'])) {
            $exists = true;
        }
    }
    if ($exists) { continue; }
    while (in_array((string)$tracker, $trackers)) { $tracker++; }
    $added[] = [
        'type'=>'pass', 'interface'=>'lan', 'ipprotocol'=>'inet', 'protocol'=>'tcp',
        'statetype'=>'keep state', 'tracker'=>(string)$tracker,
        'source'=>['address'=>'10.77.10.50'],
        'destination'=>['address'=>$destination, 'port'=>$port], 'descr'=>$description,
        'created'=>['time'=>time(), 'username'=>'admin via SSH - authorized lab setup'],
    ];
    $trackers[] = (string)$tracker++;
}
echo json_encode(['new_rules'=>$added], JSON_PRETTY_PRINT), "\n";
if (($argv[1] ?? '') !== '--apply') { exit(0); }
if (!$added) { echo "No changes needed.\n"; exit(0); }
$backup = '/conf/backup/pre-management-rules-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml', $backup)) { throw new Exception('Backup failed'); }
chmod($backup, 0600);
config_set_path('filter/rule', array_merge($added, $rules));
write_config('Add three organizer management rules for CCDC lab');
$result = filter_configure_sync();
echo 'Backup: ', $backup, "\nApply result: ", json_encode($result), "\n";
