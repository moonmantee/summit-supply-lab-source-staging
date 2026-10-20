<?php
require_once('config.inc');
echo json_encode(['interfaces'=>config_get_path('interfaces'), 'rules'=>config_get_path('filter/rule', []), 'nat_mode'=>config_get_path('nat/outbound/mode')], JSON_PRETTY_PRINT), "\n";
