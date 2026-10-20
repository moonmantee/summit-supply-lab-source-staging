<?php
// Pure helpers: only the fixed red callback can be temporarily contained.
function redContainAllow() {
    return ['type'=>'pass','interface'=>'opt4','ipprotocol'=>'inet','protocol'=>'tcp',
        'source'=>['address'=>'10.77.20.10'],
        'destination'=>['address'=>'10.77.70.10','port'=>'8770'],
        'descr'=>'RED-MARKER workstation01 callback TLS'];
}
function redContainBlock() {
    return array_replace(redContainAllow(),['type'=>'block',
        'descr'=>'RED-CONTAIN workstation01 TLS acceptance TEMP']);
}
function redContainMatches($rule,$expected) {
    foreach ($expected as $key=>$value) {
        if (($rule[$key]??null)!==$value) { throw new Exception('Conflicting containment rule scope'); }
    }
    if (isset($rule['disabled']) || isset($rule['floating']) || isset($rule['direction'])) {
        throw new Exception('Unexpected containment rule activation');
    }
}
function redContainChange($rules,$action,$tracker) {
    if (!is_array($rules) || !in_array($action,['apply','remove'],true)) { throw new Exception('Invalid containment operation'); }
    $allow=redContainAllow();$block=redContainBlock();$allowCount=0;$blockCount=0;$remaining=[];
    foreach ($rules as $rule) {
        if (!is_array($rule)) { throw new Exception('Invalid rule record'); }
        if (($rule['descr']??'')===$allow['descr']) { redContainMatches($rule,$allow);$allowCount++; }
        if (($rule['descr']??'')===$block['descr']) {
            redContainMatches($rule,$block);$blockCount++;
            if ($action==='remove' && ($rule['tracker']??'')!==(string)$tracker) { $remaining[]=$rule; }
        } else { $remaining[]=$rule; }
    }
    if ($blockCount>1 || ($action==='apply' && ($allowCount!==1 || $blockCount!==0))) {
        throw new Exception('Unexpected existing callback/containment count');
    }
    if ($action==='remove') { return $remaining; }
    if (in_array((string)$tracker,array_column($rules,'tracker'),true)) { throw new Exception('Tracker already used'); }
    $block['tracker']=(string)$tracker;$block['log']='';
    return array_merge([$block],$rules);
}
function redContainTransaction($acquire,$load,$persist,$release,$action,$tracker) {
    $key=$acquire();
    if ($key===null || $key===false) { throw new Exception('Configuration lock unavailable'); }
    try {
        $rules=$load();$new=redContainChange($rules,$action,$tracker);
        if ($new!==$rules) { $persist($new,$action); }
        return ['before'=>count($rules),'after'=>count($new),'changed'=>$new!==$rules];
    } finally { $release($key); }
}
function redContainReload($read,$reload,$pause) {
    for ($attempt=0;$attempt<3;$attempt++) {
        $read();$result=$reload();
        if ($result===0) { return 0; }
        if ($attempt<2) { $pause(); }
    }
    throw new Exception('Runtime filter reconciliation failed after3attempts');
}
