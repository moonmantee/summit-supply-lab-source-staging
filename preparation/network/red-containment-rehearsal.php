<?php
// Fixed port-only containment with generation-bound rollback and native config lock.
require_once(__DIR__.'/red-containment-functions.php');
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
$mode=$argv[1]??'--preview';
$tracker=$argv[2]??(string)time();
if (!in_array($mode,['--preview','--apply','--remove','--watchdog'],true) || !preg_match('/^[1-4][0-9]{9}$/D',$tracker) || count($argv)>3) {
    throw new Exception('Invalid fixed containment operation/tracker');
}
$ready=__DIR__.'/watchdog-'.$tracker.'.json';
if ($mode==='--watchdog') {
    $f=fopen($ready,'x');
    if ($f===false) { throw new Exception('Watchdog generation already exists'); }
    chmod($ready,0600);
    fwrite($f,json_encode(['pid'=>getmypid(),'tracker'=>$tracker,'created'=>time()]));fflush($f);fclose($f);
    echo "Generation watchdog ready\n";
    sleep(120);
    $mode='--remove';
}
$checkWatch=function()use($ready,$tracker) {
    if (is_link($ready) || !is_file($ready) || fileowner($ready)!==0 || (fileperms($ready)&0077)!==0) {
        throw new Exception('A private independent watchdog must be ready before applying');
    }
    $watch=json_decode(file_get_contents($ready),true,16,JSON_THROW_ON_ERROR);
    if (($watch['tracker']??'')!==$tracker || time()-($watch['created']??0)>30 || !posix_kill($watch['pid']??0,0)) {
        throw new Exception('Watchdog generation is not alive/fresh');
    }
};
if ($mode==='--apply') { $checkWatch(); }
$action=$mode==='--remove'?'remove':'apply';
$load=function() {
    if (!config_read_file(false,false)) { throw new Exception('Fresh configuration read failed'); }
    $interfaces=config_get_path('interfaces',[]);
    if (($interfaces['opt4']['ipaddr']??'')!=='10.77.20.1' || ($interfaces['opt2']['ipaddr']??'')!=='10.77.70.1') {
        throw new Exception('Unexpected lab interfaces');
    }
    return config_get_path('filter/rule',[]);
};
$persist=function($new,$mutation)use($checkWatch) {
    if ($mutation==='apply') { $checkWatch(); }
    $backup='/conf/backup/pre-RED-CONTAIN-'.gmdate('Ymd-His').'-'.bin2hex(random_bytes(3)).'.xml';
    if (!copy('/conf/config.xml',$backup)) { throw new Exception('Backup failed'); }
    chmod($backup,0600);
    config_set_path('filter/rule',$new);
    config_set_path('revision',make_config_revision_entry('Scoped temporary red containment acceptance'));
    // The verified native config_write_file implementation takes the same lock.
    // Persist its exact atomic write/cache invalidation while already holding it.
    if (!safe_write_file(g_get('cf_conf_path').'/config.xml',dump_xml_config(config_get_path(''),g_get('xml_rootobj')))) {
        throw new Exception('Atomic config write failed');
    }
    unlink_if_exists(g_get('tmp_path').'/config.cache');
    echo json_encode(['backup'=>$backup]),"\n";
};
if ($mode==='--preview') {
    $rules=$load();$new=redContainChange($rules,'apply',$tracker);
    echo json_encode(['operation'=>$mode,'scope'=>redContainBlock(),'tracker'=>$tracker,'before'=>count($rules),'after'=>count($new)]),"\n";
    exit(0);
}
$result=redContainTransaction(fn()=>lock('config',LOCK_EX),$load,$persist,fn($key)=>unlock($key),$action,$tracker);
echo json_encode(['operation'=>$mode,'tracker'=>$tracker]+$result),"\n";
if (!$result['changed'] && $action!=='remove') { exit(0); }
try {
    redContainReload($load,fn()=>filter_configure_sync(),fn()=>sleep(1));
    echo json_encode(['filter_result'=>0]),"\n";
} catch(Exception $error) {
    if ($action==='apply') {
        redContainTransaction(fn()=>lock('config',LOCK_EX),$load,$persist,fn($key)=>unlock($key),'remove',$tracker);
        redContainReload($load,fn()=>filter_configure_sync(),fn()=>sleep(1));
        echo json_encode(['rollback_filter_result'=>0]),"\n";
    }
    throw new Exception('Firewall reload failed; inspect rollback outcome');
}
