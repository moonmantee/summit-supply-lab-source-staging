#!/usr/bin/env bash
set -euo pipefail
test "$(id -un)" = jwang
cd /home/jwang/summit-scoring
python3 -m unittest -q test_scorer test_lifecycle test_reporting test_server
mkdir -p public state /home/jwang/.config/systemd/user
chmod 700 state
install -m 644 summit-check.service summit-check.timer summit-scoreboard.service /home/jwang/.config/systemd/user/
python3 scorer.py
systemctl --user daemon-reload
systemctl --user enable --now summit-check.timer summit-scoreboard.service
mkdir -p /home/jwang/Desktop
test ! -e /home/jwang/Desktop/Summit-Service-Scoreboard.html
cat > /home/jwang/Desktop/Summit-Service-Scoreboard.html <<'HTML'
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=http://127.0.0.1:8766/"><title>Summit service scoreboard</title></head><body><a href="http://127.0.0.1:8766/">Open the live service scoreboard</a></body></html>
HTML
systemctl --user is-active summit-check.timer summit-scoreboard.service
