<?php
require_once('config.inc');
echo json_encode(['domain'=>config_get_path('system/domain'),'hostname'=>config_get_path('system/hostname'),
    'unbound'=>config_get_path('unbound'),'ntpd'=>config_get_path('ntpd')],JSON_PRETTY_PRINT),"\n";
