<?php
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$hosts=[['workstation01','opt4','10.77.20.10'],['shop01','opt1','10.77.30.10'],['forum01','opt1','10.77.30.20'],['mail01','opt1','10.77.30.30'],['dc01','opt3','10.77.40.10'],['sql01','opt5','10.77.50.20'],['score01','opt2','10.77.70.10']];
if (!in_array('CCDC_NONINTERNET_V4',array_column(config_get_path('aliases/alias',[]),'name'))) {throw new Exception('Missing destination alias');}
$rules=config_get_path('filter/rule',[]); $added=[]; $tracker=time();
foreach ($hosts as [$name,$iface,$ip]) {
 foreach ($rules as &$rule) {
  if (($rule['descr']??'')==='CCDC '.$name.' deny direct internet') {$rule['disabled']='';}
  if (preg_match('/^CCDC '.preg_quote($name,'/').' internet TCP (80|443)$/',$rule['descr']??'')) {unset($rule['disabled']);}
 }
 unset($rule);
 $description='CCDC '.$name.' setup broad internet'; $found=false;
 foreach ($rules as &$rule) {
  if (($rule['descr']??'')===$description) {unset($rule['disabled']); $found=true;}
 }
 unset($rule);
 if (!$found) {
  while (in_array((string)$tracker,array_column(array_merge($rules,$added),'tracker'))) {$tracker++;}
  $added[]=['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>'any','tracker'=>(string)$tracker++,'source'=>['address'=>$ip],'destination'=>['address'=>'CCDC_NONINTERNET_V4','not'=>''],'statetype'=>'keep state','descr'=>$description];
 }
}
echo json_encode(['setup_hosts'=>array_column($hosts,0),'new_rules'=>count($added)],JSON_PRETTY_PRINT),"\n";
if (($argv[1]??'')!=='--apply') {exit;}
$backup='/conf/backup/pre-setup-internet-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) {throw new Exception('Backup failed');}
chmod($backup,0600);
config_set_path('filter/rule',array_merge($added,$rules));
write_config('Enable broad public IPv4 internet for all seven lab VMs during setup');
echo json_encode(['backup'=>$backup,'filter_result'=>filter_configure_sync()]),"\n";
