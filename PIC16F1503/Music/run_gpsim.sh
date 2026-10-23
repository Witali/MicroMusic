#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v gpsim >/dev/null 2>&1; then
  echo "gpsim is not installed. Debian: sudo apt install gpsim" >&2
  exit 3
fi
gpsim --version | head -5 || true
gpsim -i -c gpsim_smoke.stc > reports/gpsim_native_execution.log 2>&1
echo "Completed. See reports/gpsim_native_execution.log"
