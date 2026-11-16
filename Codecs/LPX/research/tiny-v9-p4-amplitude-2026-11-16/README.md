# Decode the two P4 amplitudes without branches on AVR25

Bit 4 is zero for amplitude −8 and has value 16 for amplitude +8.
Subtract 8 from the masked bit for each P4 pulse. The input and the
resulting signed amplitudes retain their existing wire values. All
positions and extra-pulse handling use the same parser.

The paired comparison against `e13909a0` uses AVR-GCC 7.3.0, GNU AVR ABI,
ATtiny88 at 16 MHz, 8 kHz audio, SRAM512, LPC2, FIFO32/prefill24,
MUL16 unroll2 and `-Os -flto -mcall-prologues -mrelax`. All 22
simavr 1.6 IRQ workloads save 10 program bytes, down to 4550–4551 B
excluding the embedded LPX. Decoder CPU plus IRQ time is unchanged or
lower. All 308,339 PWM samples match the baseline and portable C, with
zero underruns. Eighteen WebUI images rebuild byte for byte.
[Measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/tiny-p4-amplitude --target tiny --baseline e13909a0
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/tiny-p4-amplitude-web --run
```
