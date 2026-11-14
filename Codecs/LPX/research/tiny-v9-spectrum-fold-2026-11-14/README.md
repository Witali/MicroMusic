# Save the previous LSF index while parsing its replacement

The universal AVR25 v9 parser already stores one-based LSF indices. It now
checks one-based indices directly and saves each old index when replacing it.
A repeat uses cached LPC and needs no LSF copy. The initial LPC conversion
uses the current spectrum for both endpoints. Later absolute and delta
vectors preserve the previous and current values required by all anchors.
The original selectable C parser and the stream bytes are unchanged.

The new index is in −63..127 for a delta and 1..128 for an absolute code
before validation. Converting negative indices to `uint8_t` puts them above
the grid limit. Zero and duplicate indices fail the ordering check. The
parser retains its read order, Rice parameters and error checks.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, two LPC segments, MUL16 unroll 2, FIFO32/prefill24. Across 22 loads
in simavr 1.6 at 16 MHz and 8 kHz, the program drops by 44 B to 5146–5147 B
excluding audio. All 308,339 PWM samples match the baseline and independent
C decoder. There are zero underruns and peak stack remains 54 B. The active
decoder CPU mean plus IRQ falls by 0.28–0.62 cycles per sample. The largest
mean falls from 1655.78 to 1655.16. Peak decode CPU time drops by 140–209
cycles on every load. All 18 WebUI images rebuild byte for byte.

A separate host comparison exercises the new parser with C arithmetic on
306 Sparse80 and 303 P6 segments. PCM16 and PWM8 match for every segment.
The host comparison also matches output and API error state on 8800
deterministic bit mutations and truncated ROM or callback inputs.
[Paired measurements and aggregate counts](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/lsf-fold-final --target tiny --baseline 7bdb6b04
```
