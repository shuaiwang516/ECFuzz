#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" == "0" ]]; then
  exit 0
fi

sudo -n true >/dev/null 2>&1
