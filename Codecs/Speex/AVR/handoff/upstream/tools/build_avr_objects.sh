#!/usr/bin/env bash
# Compile a few original Xiph Speex translation units for ATmega328P.
# This intentionally stops at .o: linking the full decoder to 2KB SRAM
# requires separate PROGMEM/codebook and scratch-memory work.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:?Usage: build_avr_objects.sh /path/to/speex-1.2.1}"
SRC="$(realpath "$SRC")"
command -v avr-gcc >/dev/null || { echo 'avr-gcc not installed' >&2; exit 2; }
command -v avr-size >/dev/null || { echo 'avr-size not installed' >&2; exit 2; }
python3 "$HERE/tools/apply_upstream_port.py" "$SRC"
python3 "$HERE/tools/apply_tight_exc.py" "$SRC"
OUT="$HERE/results/avr_obj"
mkdir -p "$OUT"
for f in lsp nb_celp filters ltp cb_search quant_lsp bits; do
  echo "Compiling upstream libspeex/$f.c..."
  avr-gcc -mmcu=atmega328p -DF_CPU=16000000UL \
    -DFIXED_POINT -DDISABLE_ENCODER -DDISABLE_WIDEBAND -DDISABLE_VBR \
    -DDISABLE_FLOAT_API -DSPEEX_AVR_COMPACT_LSP -DSPEEX_AVR_FAST_MUL \
    -I"$SRC/include" -I"$SRC/libspeex" \
    -Os -fno-strict-aliasing -fwrapv -ffunction-sections -fdata-sections \
    -fstack-usage -c "$SRC/libspeex/$f.c" -o "$OUT/$f.o"
done
avr-size "$OUT"/*.o
if command -v avr-objdump >/dev/null; then
  avr-objdump -dr "$OUT/lsp.o" > "$OUT/lsp_avr.lst"
fi
echo 'AVR object build complete; this is NOT a linked ATmega328P firmware.'
