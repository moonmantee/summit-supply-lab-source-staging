<?php
// Add only the SCORE-origin flows required by score01's configured probes.
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');

$interfaces = config_get_path('interfaces', []);
foreach (['opt1'=>['em2','10.77.30.1'], 'opt2'=>['em3','10.77.70.1'],
          'opt3'=>['em4','10.77.40.1'], 'opt4'=>['em5','10.77.20.1'],
          'opt5'=>['em6','10.77.50.1']] as $name=>$expected) {
    if (($interfaces[$name]['if'] ?? '') !== $expected[0] ||
        ($interfaces[$name]['ipaddr'] ?? '') !== $expected[1]) {
        throw new Exception('Unexpected interface: '.$name);
    }
}

$source = '10.77.70.10';
$planned = [
    ['tcp/udp','10.77.40.10','53','Scorer dc01 DNS'],
    ['tcp','10.77.40.10','22','Scorer dc01 SSH'],
    ['tcp','10.77.20.10','22','Scorer workstation01 SSH'],
    ['tcp','10.77.30.10','443','Scorer shop01 HTTPS'],
    ['tcp','10.77.30.10','22','Scorer shop01 SSH'],
    ['tcp','10.77.50.20','22','Scorer sql01 SSH'],
    ['tcp','10.77.30.20','80','Scorer forum01 HTTP'],
    ['tcp','10.77.30.20','443','Scorer forum01 HTTPS after I04'],
    ['tcp','10.77.30.20','21','Scorer forum01 FTP'],
    ['tcp','10.77.30.20','22','Scorer forum01 SSH'],
    ['tcp','10.77.30.30','25','Scorer mail01 SMTP'],
    ['tcp','10.77.30.30','993','Scorer mail01 IMAPS'],
    ['tcp','10.77.30.30','443','Scorer mail01 HTTPS'],
    ['tcp','10.77.30.30','22','Scorer mail01 SSH'],
];

$rules = config_get_path('filter/rule', []);
$added = [];
$existing = [];
$tracker = time();
foreach ($planned as [$protocol,$destination,$port,$description]) {
    $desired = ['type'=>'pass','interface'=>'opt2','ipprotocol'=>'inet','protocol'=>$protocol,
                'source'=>['address'=>$source],
                'destination'=>['address'=>$destination,'port'=>$port]];
    $exact = array_values(array_filter($rules, function($rule) use ($desired) {
        foreach ($desired as $key=>$value) {
            if (($rule[$key] ?? null) !== $value) { return false; }
        }
        return !isset($rule['disabled']);
    }));
    if ($exact) {
        $existing[] = $description;
        continue;
    }
    $same_description = array_values(array_filter($rules, fn($rule)=>(($rule['descr'] ?? '') === $description)));
    if ($same_description) { throw new Exception('Conflicting rule: '.$description); }
    while (in_array((string)$tracker, array_column(array_merge($rules,$added),'tracker'))) { $tracker++; }
    $added[] = array_merge($desired, [
        'tracker'=>(string)$tracker++, 'statetype'=>'keep state', 'descr'=>$description
    ]);
}

echo json_encode(['existing'=>$existing, 'new_rules'=>$added], JSON_PRETTY_PRINT), "\n";
if (($argv[1] ?? '') !== '--apply') { exit(0); }
if (!$added) {
    echo "No configuration changes required; reloading saved rules.\n";
    echo 'Filter result: ', json_encode(filter_configure_sync()), "\n";
    exit(0);
}
$backup = '/conf/backup/pre-SCORER-RULES-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml', $backup)) { throw new Exception('Backup failed'); }
chmod($backup, 0600);
config_set_path('filter/rule', array_merge($added, $rules));
write_config('Allow score01 to perform scoped CCDC service checks');
$result = filter_configure_sync();
echo 'Filter result: ', json_encode($result), "\nBackup: $backup\n";
