#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: monitor_batch_completion.sh <batch_root> <log_file>" >&2
  exit 1
fi

BATCH_ROOT="$1"
LOG_FILE="$2"

echo "monitor_start=$(date +%Y-%m-%dT%H:%M:%S%z)" >>"${LOG_FILE}"

while true; do
  NOW="$(date +"%Y-%m-%d %H:%M:%S")"
  {
    echo "== ${NOW} =="
    cat "${BATCH_ROOT}/summary.tsv" 2>/dev/null || echo "summary.tsv missing"
    echo "-- docker --"
    docker ps --format '{{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Status}}' || true
    echo "-- fuzzer ps --"
    ps -ef | rg 'python3 src/fuzzer.py|run_docker_fuzz_single|run_docker_fuzz_all' || true
    echo
  } >>"${LOG_FILE}"

  complete=0
  if [[ -f "${BATCH_ROOT}/summary.tsv" ]]; then
    complete="$(tail -n +2 "${BATCH_ROOT}/summary.tsv" | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
  fi

  if [[ "${complete}" -ge 5 ]]; then
    echo "monitor_complete=$(date +%Y-%m-%dT%H:%M:%S%z)" >>"${LOG_FILE}"
    break
  fi

  sleep 300
done
