# Test subframe phase bits directly before reading pulses

The compact v9 parser reads P4 and P6 pulse packets every two subframes and
Sparse80 packets every four. Both tests require bit 0 to be clear. Only
Sparse80 also requires bit 1 to be clear. Testing these bits directly avoids
constructing a runtime mask. The C parser retains its equivalent mask test.

ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, LPC2, MUL16 unroll 2, FIFO32/prefill24. Compared with
`5dd70393`, the linked program shrinks by 20 B to 4822–4823 B excluding
audio. On simavr 1.6 at 16 MHz and 8 kHz, all 22 workloads produce exact PWM
for 308,339 samples with IRQ active and zero underruns. Each saves 0.505–0.657
mean decoder CPU cycles per sample including IRQ. Peak CPU time decreases by
9–12 cycles and peak stack stays at 53 B. All 18 published WebUI images
rebuild byte for byte. [Paired IRQ measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/pulse-schedule-matched --target tiny --baseline 5dd70393
```
