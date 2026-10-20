<?php
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$mode=$argv[1]??'--preview';
$hosts=[
 ['workstation01','opt4','10.77.20.10','10.77.20.1'],
 ['shop01','opt1','10.77.30.10','10.77.30.1'],
 ['forum01','opt1','10.77.30.20','10.77.30.1'],
 ['mail01','opt1','10.77.30.30','10.77.30.1'],
 ['dc01','opt3','10.77.40.10','10.77.40.1'],
 ['sql01','opt5','10.77.50.20','10.77.50.1'],
 ['score01','opt2','10.77.70.10','10.77.70.1']
];
$interfaces=config_get_path('interfaces',[]);
foreach($hosts as [$name,$iface,$ip,$gateway]) {
 if(($interfaces[$iface]['ipaddr']??'')!==$gateway) throw new Exception('Wrong interface '.$name);
}
if(($interfaces['lan']['ipaddr']??'')!=='10.77.10.1') throw new Exception('Wrong LAN');
if(config_get_path('nat/outbound/mode')!=='automatic') throw new Exception('Unexpected NAT mode');
$original=config_get_path('filter/rule',[]); $rules=$original;
$added=[]; $removed=[]; $enabled=[]; $tracker=time();
function addflow($iface,$src,$dst,$proto,$port,$description) {
 global $rules,$added,$tracker;
 $desired=['type'=>'pass','interface'=>$iface,'ipprotocol'=>'inet','protocol'=>$proto,'source'=>['address'=>$src],'destination'=>['address'=>$dst]];
 if($port!=='') $desired['destination']['port']=$port;
 foreach($rules as $r) {
  if(isset($r['disabled'])) continue;
  $match=true;
  foreach($desired as $key=>$v) if(($r[$key]??null)!==$v) $match=false;
  if($match) return;
 }
 while(in_array((string)$tracker,array_column($rules,'tracker'))) $tracker++;
 $r=$desired+['tracker'=>(string)$tracker++,'statetype'=>'keep state','descr'=>$description];
 $rules[]=$r; $added[]=$r;
}
foreach($hosts as [$name,$iface,$ip,$gateway]) {
 addflow('lan','10.77.10.50',$ip,'tcp','22','Organizer SSH to '.$name);
 addflow($iface,$ip,$gateway,'tcp/udp','53','CCDC '.$name.' gateway DNS');
 addflow($iface,$ip,$gateway,'udp','123','CCDC '.$name.' gateway NTP');
 addflow($iface,$ip,'10.77.0.0/16','icmp','','CCDC '.$name.' lab diagnostics');
 if(!in_array($name,['dc01','score01'])) {
  foreach(['tcp'=>['53','88','135','389','445','464','636','3268','3269','49152-65535'],'udp'=>['53','88','123','389','464']] as $proto=>$ports) {
   foreach($ports as $port) addflow($iface,$ip,'10.77.40.10',$proto,$port,'CCDC '.$name.' domain '.$proto.' '.$port);
  }
 }
}
// Business workstation accesses the actual business services, not unrestricted inter-zone traffic.
foreach([['10.77.30.10',['80','443']],['10.77.30.20',['21','80','443']],['10.77.30.30',['25','143','443','587','993']],['10.77.70.10',['8080']]] as [$dst,$ports]) {
 foreach($ports as $port) addflow('opt4','10.77.20.10',$dst,'tcp',$port,'Business service '.$dst.' TCP '.$port);
}
foreach([['10.77.30.10',['80','443']],['10.77.30.20',['21','80','443','3389']],['10.77.30.30',['25','143','443','587','993','3389']],['10.77.40.10',['3389']],['10.77.70.10',['8080']],['10.77.20.10',['8080']]] as [$dst,$ports]) {
 foreach($ports as $port) addflow('lan','10.77.10.50',$dst,'tcp',$port,'Organizer service '.$dst.' TCP '.$port);
}
// Read from forum01's live IIS firewallSupport configuration on 2026-10-12.
foreach([['opt2','10.77.70.10'],['opt4','10.77.20.10'],['lan','10.77.10.50']] as [$iface,$src]) {
 addflow($iface,$src,'10.77.30.20','tcp','40000-40049','CCDC FTP passive data from '.$src);
}
// Put scoped additions before old catch-all rules and SCORE protection blocks.
$addedTrackers=array_column($added,'tracker');
$rules=array_merge($added,array_values(array_filter($rules,fn($r)=>!in_array($r['tracker']??'', $addedTrackers,true))));
$final=[];
foreach($rules as $r) {
 $descr=$r['descr']??'';
 $proxy=preg_match('/^CCDC \S+ score01 proxy$/',$descr);
 $oldInternetBlock=preg_match('/^CCDC \S+ deny direct internet$/',$descr);
 $broad=($r['type']??'')==='pass' && isset($r['source']['any']) && isset($r['destination']['any']) && !isset($r['destination']['port']);
 $setup=preg_match('/^CCDC \S+ setup broad internet$/',$descr);
 $oldDefault=in_array($r['tracker']??'', ['0100000101','0100000102'],true);
 if($proxy || $oldInternetBlock || ($mode==='--tighten' && ($broad || $setup || $oldDefault))) {
  $removed[]=['tracker'=>$r['tracker'],'description'=>$descr,'interface'=>$r['interface']]; continue;
 }
 if($mode==='--trial' && ($broad || $setup || $oldDefault)) $r['disabled']='';
 if(preg_match('/^CCDC \S+ internet TCP (80|443)$/',$descr)) { unset($r['disabled']); $enabled[]=$r['tracker']; }
 if(preg_match('/^CCDC \S+ score01 downloads$/',$descr)) $r['descr']=str_replace('downloads','team portal',$descr);
 $final[]=$r;
}
// Ensure all seven public HTTP/HTTPS pairs exist and are active before changing anything.
foreach($hosts as [$name,$iface,$ip,$gateway]) foreach(['80','443'] as $port) {
 $found=false;
 foreach($final as $r) if(!isset($r['disabled']) && ($r['type']??'')==='pass' && ($r['interface']??'')===$iface && ($r['protocol']??'')==='tcp' && ($r['source']['address']??'')===$ip && ($r['destination']['address']??'')==='CCDC_NONINTERNET_V4' && isset($r['destination']['not']) && ($r['destination']['port']??'')===$port) $found=true;
 if(!$found) throw new Exception('Missing direct web rule '.$name.' '.$port);
}
$aliases=config_get_path('aliases/alias',[]);
if(!in_array('CCDC_NONINTERNET_V4',array_column($aliases,'name'))) throw new Exception('Missing public destination alias');
echo json_encode(['mode'=>$mode,'added'=>$added,'removed'=>$removed,'enabled_web'=>$enabled,'final_count'=>count($final)],JSON_PRETTY_PRINT),"\n";
if(!in_array($mode,['--prepare','--trial','--tighten'],true)) exit;
$backup='/conf/backup/pre-range-cleanup-'.gmdate('Ymd-His').'-'.substr($mode,2).'.xml';
if(!copy('/conf/config.xml',$backup)) throw new Exception('Backup failed');
chmod($backup,0600);
config_set_path('filter/rule',$final);
write_config('CCDC: retire score proxy; explicit routed services and direct web access; phase '.$mode);
foreach($aliases as $a) alias_make_table($a);
$result=filter_configure_sync();
echo json_encode(['backup'=>$backup,'filter_result'=>$result]),"\n";
if($result!==0) throw new Exception('Firewall reload did not return success');
