# Adjust the split polynomial quotient and remainder together

For a negative coefficient with nonzero low nibble, increment the arithmetic
quotient and subtract 16 from the remainder. The resulting pair matches
division toward zero, including exact multiples of 16. The two Q12 product
rounding points and the wire data remain unchanged. A scalar check covers
all 1,032,193 values in the bounded polynomial operand range.

ATtiny88 / AVR25, AVR-GCC 7.3.0, GNU AVR ABI, `-Os -flto -mcall-prologues
-mrelax`, two LPC segments, MUL16 unroll 2, FIFO32/prefill24. Compared with
`38d0d499`, the program falls by 20 B to 5046–5047 B excluding audio. In
simavr 1.6 at 16 MHz and 8 kHz, 21 of 22 workloads speed up by up to 0.122
decoder CPU cycles per sample including IRQ. One ties. The peak CPU cost
of a decode call falls by 5–35 cycles on every workload. All 308,339 PWM
samples match the baseline and independent C output, with zero underruns.
Peak stack and the minimum queue occupancy on each workload are unchanged.
All 18 WebUI images rebuild byte for byte.
[Paired measurements](measurements.json).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py \
  build/poly-quotient-matched --target tiny --baseline 38d0d499
```
