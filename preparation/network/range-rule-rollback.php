<?php
// Started before the trial. Cancellation is explicit after final verification.
$backup=$argv[1]??'';
$cancel='/root/range-rule-trial-20261012.accepted';
if(!preg_match('#^/conf/backup/pre-range-cleanup-[0-9-]+-prepare\.xml$#',$backup) || !is_file($backup)) exit(2);
sleep(1800);
if(is_file($cancel)) exit(0);
require_once('config.inc');
require_once('functions.inc');
require_once('filter.inc');
require_once('shaper.inc');
// Restore only filter rules; preserve any concurrent unrelated configuration.
$parsed=parse_xml_config($backup,'pfsense');
if(!isset($parsed['filter']['rule'])) exit(4);
config_set_path('filter/rule',$parsed['filter']['rule']);
write_config('Automatic recovery: CCDC firewall trial not accepted before deadline');
echo 'RECOVERY_RESULT=',filter_configure_sync(),"\n";
