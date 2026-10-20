<?php
require_once('config.inc');
require_once('functions.inc');
require_once('system.inc');
system_ntp_configure();
echo "NTP restarted using pfSense configuration.\n";
