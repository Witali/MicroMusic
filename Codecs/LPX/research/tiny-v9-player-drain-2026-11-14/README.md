# Share the foreground drain and stop path on AVR25

On universal v9, normal EOF and decode failure both join the same foreground
drain. If playback has started, the IRQ consumes the queued prefix before the
player stops the timer. Before startup, a malformed prefix is discarded. The
final sample and EOF remain a single atomic publication. The selectable C
player and fixed-header recipes retain their existing implementation.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, two LPC segments, MUL16 unroll 2 and FIFO32/prefill24.
Compared with `4c8d799c`, program Flash drops by 66 B to 4958–4959 B
excluding the identical audio. All 22 workloads in simavr 1.6 at 16 MHz and
8 kHz match the baseline and independent C PWM. All 308,339 samples play
without underruns. Decoder mean plus IRQ and peak stack stay the same.

Fourteen additional comparisons cover invalid headers, invalid initial
spectra, a truncated stream after startup, nine short or partial playback
lengths, and two repeat counts. The truncated stream drains the same 6000
samples before stopping with the same error. All 18 WebUI images rebuild
byte for byte. [Per-load measurements and playback controls](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/eof-drain-matched --target tiny --baseline 4c8d799c
```
