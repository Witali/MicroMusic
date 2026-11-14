# Omit the restart branch from single-playback AVR25 firmware

Successful playback publishes the final sample and EOF atomically. The next
foreground iteration enters the drain. The universal v9 build can omit the
redundant stream restart check when `LPX25_REPEAT` is one. Builds configured
for multiple playbacks still call `begin()` between repetitions. The stream
format, arithmetic backends and sample IRQ are unchanged.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, two LPC segments, MUL16 unroll 2 and FIFO32/prefill24.
Compared with `c0f3d76c`, program Flash drops by 34 B to 4924–4925 B
excluding audio. Across 22 simavr 1.6 workloads at 16 MHz and 8 kHz, all
308,339 PWM samples match the baseline and independent C output. Mean
active decoder CPU time plus IRQ is one cycle per sample lower across the
matrix. Peak stack stays at 53 B, with zero underruns. All 18 WebUI images
rebuild byte for byte.

Fourteen paired playback controls cover header and initial spectrum errors,
active truncation, short and partial tails, and two- and four-playback
builds. The output, error status and final state agree with the baseline.
[Per-load measurements and playback controls](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/one-shot-matched --target tiny --baseline c0f3d76c
```
