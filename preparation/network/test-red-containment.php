<?php
require_once(__DIR__.'/red-containment-functions.php');
function check($condition) { if (!$condition) { throw new Exception('Test assertion failed'); } }
$allow = redContainAllow();
$base = [['descr'=>'existing business rule','type'=>'pass'], $allow];
$added = redContainChange($base, 'apply', 12345);
check(count($added)===3 && $added[0]['destination']['port']==='8770');
check(array_slice($added,1)===$base);
check(redContainChange($added,'remove',12345)===$base);
check(redContainChange($added,'remove',54321)===$added);
check(redContainChange($base,'remove',12345)===$base);
$concurrent=$added; $concurrent[]=['descr'=>'new competitor rule','type'=>'block'];
check(array_slice(redContainChange($concurrent,'remove',12345),0,2)===$base);
check(count(redContainChange($concurrent,'remove',12345))===3);
foreach (['port','source','disabled','duplicate'] as $change) {
    $bad=$added;
    if ($change==='port') { $bad[0]['destination']['port']='8080'; }
    if ($change==='source') { $bad[0]['source']['address']='10.77.20.0/24'; }
    if ($change==='disabled') { $bad[0]['disabled']=''; }
    if ($change==='duplicate') { $bad[]=$bad[0]; }
    $rejected=false;
    try { redContainChange($bad,'remove',12345); } catch (Exception $e) { $rejected=true; }
    check($rejected);
}
$rejected=false;
try { redContainChange([], 'apply', 12345); } catch (Exception $e) { $rejected=true; }
check($rejected);
$calls=[];$live=$base;
$result=redContainTransaction(
    function()use(&$calls,&$live){$calls[]='lock';$live[]=['descr'=>'concurrent insertion','type'=>'pass'];return true;},
    function()use(&$calls,&$live){$calls[]='fresh-read';return $live;},
    function($new)use(&$calls,&$live){$calls[]='persist';$live=$new;},
    function($key)use(&$calls){$calls[]='unlock';},'apply',98765);
check($calls===['lock','fresh-read','persist','unlock']);
check(count($live)===4 && $live[3]['descr']==='concurrent insertion');
$reloads=0;$reads=0;$sleeps=0;
redContainReload(function()use(&$reads){$reads++;},
    function()use(&$reloads){$reloads++;return $reloads===1?1:0;},
    function()use(&$sleeps){$sleeps++;});
check($reloads===2 && $reads===2 && $sleeps===1);
$rejected=false;
try { redContainReload(fn()=>null,fn()=>1,fn()=>null); } catch(Exception $e) { $rejected=true; }
check($rejected);
$deadWatchdog=true;$saved=null;
redContainTransaction(fn()=>true,fn()=>$added,
    function($new,$mutation)use($deadWatchdog,&$saved){
        if($mutation==='apply' && $deadWatchdog)throw new Exception('Watchdog dead');
        $saved=$new;
    },fn($key)=>null,'remove',12345);
check($saved===$base);
echo "Containment scope, rollback, idempotent removal and conflict tests passed\n";
