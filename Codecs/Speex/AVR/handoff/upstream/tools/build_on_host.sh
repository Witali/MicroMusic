#!/usr/bin/env bash
set -euo pipefail
# Usage: tools/build_on_host.sh /path/to/unpacked/speex-1.2.1
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:?Please specify extracted official source directory}"
SRC="$(realpath "$SRC")"
python3 "$HERE/tools/apply_upstream_port.py" "$SRC"
python3 "$HERE/tools/apply_tight_exc.py" "$SRC"
mkdir -p "$HERE/results/build_ref" "$HERE/results/build_compact" "$HERE/results/build_tight"
# Out-of-tree configure builds keep the upstream tree intact apart from
# the guarded lsp.c addition. Both have fixed-point and no floating API.
for mode in ref compact tight; do
  B="$HERE/results/build_$mode"
  extra=""
  if [[ "$mode" != ref ]]; then extra="-DSPEEX_AVR_COMPACT_LSP"; fi
  if [[ "$mode" == tight ]]; then extra="$extra -DSPEEX_AVR_TIGHT_EXC"; fi
  if [[ ! -f "$B/Makefile" ]]; then
    (cd "$B"; "$SRC/configure" --enable-fixed-point --disable-float-api --disable-vbr \
       CFLAGS="-O2 -g -fno-strict-aliasing $extra -DDISABLE_ENCODER -DDISABLE_WIDEBAND")
  fi
  make -C "$B/libspeex" -j2
  echo "Ready: $B/libspeex/.libs/libspeex.so*"
done
