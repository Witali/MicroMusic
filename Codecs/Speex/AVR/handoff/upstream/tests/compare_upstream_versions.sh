#!/usr/bin/env bash
# Build-on-host must have completed successfully. Then compare fixed-point
# libspeex 1.2.1 from the same source with compact LSP on/off.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="$HERE/results/build_ref/libspeex/.libs/libspeex.so"
OPT="$HERE/results/build_compact/libspeex/.libs/libspeex.so"
TIGHT="$HERE/results/build_tight/libspeex/.libs/libspeex.so"
[[ -f "$REF" && -f "$OPT" && -f "$TIGHT" ]] || { echo 'Build upstream first: tools/build_on_host.sh /path/to/speex-1.2.1' >&2; exit 2; }
mkdir -p "$HERE/results/pcm_comparison"
for file in "$HERE"/baseline_R4/Speex_AVR_LSP_R4/data/*.spxraw; do
  stem="$(basename "$file" .spxraw)"
  SPEEX_LIBRARY="$REF" python3 "$HERE/tests/decode_with_system_speex.py" "$file" --wav "$HERE/results/pcm_comparison/$stem.ref.wav"
  SPEEX_LIBRARY="$OPT" python3 "$HERE/tests/decode_with_system_speex.py" "$file" --wav "$HERE/results/pcm_comparison/$stem.compact.wav"
  SPEEX_LIBRARY="$TIGHT" python3 "$HERE/tests/decode_with_system_speex.py" "$file" --wav "$HERE/results/pcm_comparison/$stem.tight.wav"
  cmp "$HERE/results/pcm_comparison/$stem.ref.wav" "$HERE/results/pcm_comparison/$stem.compact.wav"
  cmp "$HERE/results/pcm_comparison/$stem.ref.wav" "$HERE/results/pcm_comparison/$stem.tight.wav"
  echo "PCM equal: $stem"
done
