# Compact dense pulse packets on ATtiny88

The universal v9 AVR25 parser decodes the base P4 pulses directly and reads
both signed P6 amplitudes as one byte. The high-coordinate table already
bounds the P6 positions after the encoded index check. A forward insertion
pass places an extra pulse or merges coincident amplitudes. Two explicit
subtractions turn the sorted positions into countdowns. The selectable C
decoder retains its equivalent parser.

AVR-GCC 7.3.0 generates a smaller LSF converter when code hoisting is
disabled locally. The packet change alone saved 24 bytes and added up to
0.0061 cycles/sample on Sparse80 controls. The assembler and linker layout
from the local converter option removes that increase in the paired build.

ATtiny88, GNU AVR ABI, 16 MHz, 8 kHz, SRAM512, LPC2, MUL16 unroll2,
FIFO32/prefill24 and `-Os -flto -mcall-prologues -mrelax`. Compared with
`1fe7048d`, every one of the 22 images saves 46 program bytes and keeps its
audio unchanged. Program Flash ranges from 4776 to 4777 bytes. With IRQ
active in simavr 1.6, all 308,339 PWM samples match the baseline and the
independent C decoder. The mean active decoder time including IRQ drops
by 0.205–4.664 cycles/sample. Peak decoder work drops by 134–295 cycles.
Peak stack drops from 53 to 51 bytes. Queue occupancy stays at or above
24 samples in the tests and output has zero underruns.

Additional IRQ runs exercise all 40 extra-pulse positions for P4 and P6
including exact collisions, an out-of-range P6 pair, an out-of-range extra
and a truncated amplitude packet. The malformed cases drain the same
1200-sample PWM prefix and return the same error as the baseline. The
18 release images tracked at the baseline revision rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/pulse-packets-matched --target tiny --baseline 1fe7048d
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/pulse-packets-web --run
```
