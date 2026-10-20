<?php
// Read-only TCP probes from real range-fw interfaces; no policy writes.
$target = '10.77.30.10';
$cases = ['ssh_allowed'=>['10.77.30.1',22], 'http'=>['10.77.30.1',80],
          'https'=>['10.77.30.1',443], 'marker'=>['10.77.30.1',30303],
          'ssh_unapproved'=>['10.77.50.1',22]];
$results=[];
foreach ($cases as $name=>$case) {
    $context=stream_context_create(['socket'=>['bindto'=>$case[0].':0']]);
    $socket=@stream_socket_client('tcp://'.$target.':'.$case[1],$errno,$message,3,STREAM_CLIENT_CONNECT,$context);
    $results[$name]=is_resource($socket);
    if (is_resource($socket)) fclose($socket);
}
echo json_encode($results)."\n";
