#!/usr/bin/env bash
# Native parser diagnostic only; never start sshd or change production config.
set -euo pipefail
probe_tmp=$(mktemp -d /tmp/summit-sshd-parser-XXXXXXXX)
cleanup() { rm -f -- "$probe_tmp/key" "$probe_tmp/key.pub"; rmdir -- "$probe_tmp"; }
trap cleanup EXIT
ssh-keygen -q -t ed25519 -N '' -f "$probe_tmp/key"
printf 'AllowUsers jwang summit_editor\n' | /usr/sbin/sshd -T -h "$probe_tmp/key" -f /dev/stdin -C user=jwang,host=shop01,addr=10.77.10.1 | sed -n '/^allowusers /p; /^allowgroups /p; /^denygroups /p; /^authorizedkeyscommand /p'
