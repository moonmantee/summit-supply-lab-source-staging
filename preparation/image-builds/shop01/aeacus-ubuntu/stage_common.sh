#!/usr/bin/env bash
# Inherited rollback handler, including failures inside nested Bash functions.
summit_on_error() {
  local failure_status=$1
  trap - ERR
  if rollback; then
    printf '%s\n' 'Batch failed; original batch state restored.' >&2
  else
    printf '%s\n' 'ROLLBACK FAILED: use the printed private backup and console recovery.' >&2
    exit 90
  fi
  exit "$failure_status"
}
enable_rollback_trap() {
  declare -F rollback >/dev/null || return 1
  set -E
  trap 'summit_on_error "$?"' ERR
}
