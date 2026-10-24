#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# No external sources required; compiles and tests the two polynomial recurrences.
gcc -O2 -std=c99 -Wall -Wextra -Werror -fwrapv -fstack-usage \
    "$HERE/tests/verify_compact_lsp.c" -lm -o "$HERE/tests/verify_compact_lsp"
"$HERE/tests/verify_compact_lsp"
python3 "$HERE/tests/verify_exc_history.py"
python3 "$HERE/tests/verify_patcher_fixture.py"
python3 -m py_compile "$HERE/tools/"*.py "$HERE/tests/"*.py
# The original upstream Speex source is not embedded in the archive.
if command -v clang >/dev/null; then
  clang -target avr -mmcu=atmega328p -O3 -ffreestanding \
      -I"$HERE/baseline_R4/Speex_AVR_LSP_R4/src/test_shims" \
      -c "$HERE/tests/test_fastmul_avr.c" -o "$HERE/tests/test_fastmul_avr.o"
  echo 'AVR fastmul object compilation: OK'
fi
python3 "$HERE/tests/decode_with_system_speex.py" \
    "$HERE/baseline_R4/Speex_AVR_LSP_R4/data/speech_ru.spxraw" \
    --wav "$HERE/results/system_speex_speech.wav"
echo 'Local tests: PASS'
