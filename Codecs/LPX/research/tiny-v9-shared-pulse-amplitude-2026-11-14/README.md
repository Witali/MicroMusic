# Share the signed four-bit pulse amplitude decoder

P6 base pulses and the optional extra pulse use the same signed four-bit
field. One `signedPulseAmplitude` function now decodes both. On universal
AVR25 v9 the expression `(raw ^ 8) - 8` maps the nibble to −8..7. The
original comparison and subtraction remain the selectable C implementation.
Both callers read the same number of bits and retain their existing order,
position validation and collision handling.

On ATtiny88 with GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto -mcall-prologues
-mrelax`, SRAM512, LPC2, MUL16 unroll 2 and FIFO32/prefill24, the linked
program shrinks by 4 B to 4870–4871 B excluding audio. At 16 MHz and 8 kHz,
22 simavr 1.6 workloads match the independent C reference and paired AVR
output for all 308,339 PWM samples. The mean decoder CPU time plus the
complete IRQ changes by −0.0563 to +0.0441 cycles/sample. Six P4 workloads
show the increase. Peak decoder cost, stack and queue occupancy do not
regress. There are zero underruns. The seven native v9 tests pass and all
18 published WebUI images rebuild byte for byte.

Together with the shared pulse position function, the two extractions save
28 B and reduce the mean decoder time by 0.050–0.251 cycles/sample on all
22 workloads relative to `974942f`.
[Paired measurements for amplitude extraction](measurements.json).
