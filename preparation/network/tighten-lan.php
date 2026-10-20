<?php
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$rules=config_get_path('filter/rule',[]);
foreach (['Organizer SSH to shop01','Organizer SSH to score01','Organizer HTTPS to shop01'] as $required) {
    $found=false;
    foreach ($rules as $rule) {
        if (($rule['descr']??'')===$required && !isset($rule['disabled']) && ($rule['interface']??'')==='lan') { $found=true; }
    }
    if (!$found) { throw new Exception('Missing management rule: '.$required); }
}
$backup='/conf/backup/pre-lan-tightening-'.gmdate('Ymd-His').'.xml';
if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
chmod($backup,0600);
$disabled=[];
foreach ($rules as &$rule) {
    if (($rule['interface']??'')==='lan' &&
        in_array($rule['tracker']??'', ['0100000101','0100000102'],true) &&
        ($rule['source']['network']??'')==='lan' && isset($rule['destination']['any'])) {
        $rule['disabled']='';
        $disabled[]=$rule['descr'];
    }
}
unset($rule);
$extra=[];
$tracker=time();
foreach (['22'=>'Organizer SSH to firewall','443'=>'Organizer HTTPS to firewall'] as $port=>$description) {
    if (in_array($description,array_column($rules,'descr'))) { continue; }
    $extra[]=['type'=>'pass','interface'=>'lan','ipprotocol'=>'inet','protocol'=>'tcp','tracker'=>(string)$tracker++,
        'source'=>['address'=>'10.77.10.50'],'destination'=>['address'=>'10.77.10.1','port'=>(string)$port],
        'statetype'=>'keep state','descr'=>$description];
}
config_set_path('filter/rule',array_merge($extra,$rules));
write_config('Disable default broad LAN allows after verified guest migration; retain anti-lockout and explicit organizer access');
echo json_encode(['disabled'=>$disabled,'backup'=>$backup,'apply_result'=>filter_configure_sync()],JSON_PRETTY_PRINT),"\n";
