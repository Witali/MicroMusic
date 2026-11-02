# Compose finite control maps before the signal loop

Measured target: ATmega328P / classic AVR5, GNU ABI, AVR GCC 7.3.0, existing
Os/O2/O3, LTO, mcall-prologues and mrelax. Benefit: speed and Flash, unchanged
working RAM. The gain operation is portable C with independent table-memory
access; no handwritten ASM is added. Original project derivation from pinned
Xiph Speex 1.2.1 formulas; retain existing BSD provenance.

NB1 has sixteen coefficient codes. Apply both complete original rounded maps
and the final clamp to each code, retaining negative floors/ties and coefficient
code15 ->64. The exact final gains fit sixteen Flash bytes:

```c
{0,0,0,0,6,12,20,26,32,38,45,51,57,63,64,64}
```

Preserve all noise, gain and signal quantizers. Hardware Flash reads remain
independent of ASM enablement. Keep an explicit portable arithmetic reference
and verify the full domain, actual LPM addresses and GNU ABI.

The direct scalar lookup is 11 cycles / 0 MULs including RET, versus 298..301 /
9 for the original. A redundant `if(g>64)g=64` costs three scalar cycles, yet
makes the standalone NB caller 156 cycles/frame faster than direct lookup.
WB prefers the direct read. Select the measured recipe at compile time with
the existing profile flag; source operation counts and scalar benchmarks alone
do not establish caller performance.

Full NB2.15/WB3.95 speech CPU improves 32.001% ->31.904% and 69.566% ->69.474%,
82 B less Flash each, unchanged static SRAM/peak stack and exact PCM. Fresh
paired raw, +8%/+11% IRQ and actual SPI retain exact PCM/PWM without underruns.
This is ISA-simulator evidence, not board or other-architecture performance.
ASM-enabled/disabled scalar binaries are byte-identical; only isolated C
controls execute, never the C decoder.

[Map and portable reference](../../Codecs/Speex/AVR/src/nb1_gain.h),
[controller](../../Codecs/Speex/AVR/src/lowrate_excitation.h),
[scope, resources and reproduction](../../Codecs/Speex/AVR/WB_GAIN_MAP.md).

## Further identities: host-checked, not admitted on target

These original derivations have only exhaustive host-integer formula checks;
they are not compiled/benchmarked target improvements yet:

```c
/* signed16 a; now is original floor(22938*a/32768). */
previous_pulse = a - now - (((uint16_t)a & 16383u) != 0);
/* Exactly floor(9830*a/32768): weights sum to 32768, gcd is 2. */

/* g in 0..64; unsigned modulo arithmetic preserves the word. */
previous_gain = 77u*g;
noise_gain = (uint16_t)(32767u - ((uint16_t)g<<9) + previous_gain);
/* Exactly 32767-435*g because 435+77=512. */

/* Every signed16 n, including -32768. */
unity_q15 = n - (n>0) + (n==INT16_MIN);
/* Exactly floor(32767*n/32768). */
```

Host checks cover all 65536 pulse amplitudes, all 65 gains and all 65536 unity-Q15
inputs. Retain bounds/casts when adapting. Gain-zero preparation could avoid
pulse/previous-noise products, but must still generate noise, retain the prior
pulse, update state and preserve all 160 RNG steps. Do not interpret zero pulse
gain as silence or use completed innovation as prediction. Measure compiled
callers, stack and loaded IRQ/SPI before accepting these optimizations.
