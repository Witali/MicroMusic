#!/usr/bin/env bash
# This script has NOT been exercised against official MDB in this environment.
# It uses published third-party Docker images containing MPLAB X.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$PWD"
if ! command -v docker >/dev/null 2>&1; then
  echo 'ERROR: Docker CLI not installed; no MPLAB download or simulation was performed.' >&2
  exit 10
fi
if ! docker info >/dev/null 2>&1; then
  echo 'ERROR: Docker daemon unavailable.' >&2
  exit 11
fi
python3 - <<'PY'
from pathlib import Path
import hashlib
p=Path('micromusic_with_config.hex')
expected='7787e6dae4f115a36cf4f4a9054ed02c74411106efb02ba861195755854ae578'
actual=hashlib.sha256(p.read_bytes()).hexdigest()
print('PIC HEX SHA-256:', actual)
if actual != expected: raise SystemExit('Wrong PIC HEX checksum')
PY
images=(
  'mpfitzpatrick/mplabx-build:v2.31-mplabx5.45'
  'dataspeedinc/mplabx:mplab_5.40_xc32_2.50'
)
if [[ $# -ge 1 ]]; then images=("$1"); fi
for IMAGE in "${images[@]}"; do
  echo "Trying official MPLAB X installed in third-party container: $IMAGE"
  if ! docker pull "$IMAGE"; then
    echo "Download failed: $IMAGE" >&2
    continue
  fi
  echo "$IMAGE" > docker_image_used.txt
  # Run via the native MDB command script; no JavaScript MCU emulation here.
  set +e
  docker run --rm -v "$HERE:/work:rw" -w /work --entrypoint /bin/sh "$IMAGE" -c '
    MDB=$(find /opt/microchip -type f -name mdb.sh 2>/dev/null | head -n 1)
    if [ -z "$MDB" ]; then
      echo "ERROR: Official mdb.sh missing from Docker image" > /work/mdb_official_output.log
      exit 12
    fi
    echo "MDB executable: $MDB" > /work/mdb_official_output.log
    "$MDB" /work/mdb_check.txt >> /work/mdb_official_output.log 2>&1
    result=$?
    cat /work/mdb_official_output.log
    exit "$result"
  '
  code=$?
  set -e
  echo "Official MDB process exit code: $code"
  if [ "$code" = 0 ] && grep -q 'CHECKPOINT_4096' mdb_official_output.log; then
    echo 'MDB completed 4096 instruction checkpoints. Checking reference values.'
    python3 compare_logs.py | tee comparison_result.txt
    echo 'Inspect comparison_result.txt and mdb_official_output.log.'
    exit 0
  fi
  echo 'Simulator did not finish valid checkpoints; checking next available image.' >&2
done
echo 'ERROR: No MPLAB X Simulator succeeded. No independent validation.' >&2
exit 20
