#!/bin/sh
set -eu
test ! -e /root/range-rule-trial-20261012.accepted
backup=/conf/backup/pre-range-cleanup-$(date -u +%Y%m%d-%H%M%S)-prepare.xml
test ! -e "$backup"
cp -p /conf/config.xml "$backup"
chmod 600 "$backup"
nohup /usr/local/bin/php /root/range-rule-rollback.php "$backup" </dev/null >/root/range-rule-rollback-20261012.log 2>&1 &
pid=$!
echo "$pid" >/root/range-rule-rollback-20261012.pid
kill -0 "$pid"
echo "Recovery armed: $backup; PID $pid; 30 minutes"
/usr/local/bin/php /root/finalize-range-rules.php --trial
/sbin/pfctl -nf /tmp/rules.debug
