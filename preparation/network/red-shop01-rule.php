<?php
// Narrow organizer-approved shop01 exercise callback. Default is preview only.
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$interfaces=config_get_path('interfaces', []);
if (($interfaces['opt1']['ipaddr'] ?? '')!=='10.77.30.1' ||
    ($interfaces['opt2']['ipaddr'] ?? '')!=='10.77.70.1') {
    throw new Exception('Unexpected DMZ/SCORE identities');
}
$desired=['type'=>'pass','interface'=>'opt1','ipprotocol'=>'inet','protocol'=>'tcp',
    'source'=>['address'=>'10.77.30.10'],'destination'=>['address'=>'10.77.70.10','port'=>'8770']];
$description='RED-SHOP01 bounded exercise callback TLS';
$rules=config_get_path('filter/rule', []);
$found=[];
foreach ($rules as $i=>$rule) {
    if (($rule['descr'] ?? '')!==$description) continue;
    foreach ($desired as $k=>$v) {
        if (($rule[$k] ?? null)!==$v || isset($rule['disabled'])) throw new Exception('Changed rule preserved');
    }
    $found[]=$i;
}
if (count($found)>1) throw new Exception('Duplicate rule requires organizer review');
$mode=$argv[1] ?? '--preview';
if (!in_array($mode,['--preview','--apply','--remove'],true)) throw new Exception('Unknown mode');
echo json_encode(['mode'=>$mode,'rule'=>$desired,'already_exists'=>count($found)===1]), "\n";
if ($mode==='--preview' || ($mode==='--apply' && count($found)===1) || ($mode==='--remove' && !$found)) exit(0);
$backup='/conf/backup/pre-RED-SHOP01-'.gmdate('Ymd-His').'-'.bin2hex(random_bytes(4)).'.xml';
if (!copy('/conf/config.xml',$backup)) throw new Exception('Backup failed');
chmod($backup,0600);
if ($mode==='--remove') {
    unset($rules[$found[0]]);$rules=array_values($rules);
} else {
    $tracker=time();
    while (in_array((string)$tracker,array_column($rules,'tracker'),true)) $tracker++;
    array_unshift($rules,array_merge($desired,['tracker'=>(string)$tracker,'statetype'=>'keep state','descr'=>$description]));
}
config_set_path('filter/rule',$rules);
write_config('Scoped shop01 red-team callback '.$mode.'; preserve scoring and other firewall rules');
$result=filter_configure_sync();
echo json_encode(['backup'=>$backup,'filter_result'=>$result,'rules'=>count($rules)]), "\n";
if ($result!==0) throw new Exception('Filter reload failed; inspect saved configuration and backup');
