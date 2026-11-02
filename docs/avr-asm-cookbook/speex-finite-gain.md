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

## Admit an exactly zero control result without suppressing the signal

Gain codes 0..3 produce exactly zero pulse gain. Skip the original square root,
new pulse/previous-noise products and use `n-(n>0)` for the current noise's
gain 32767. The noise bound -14771..14771 excludes -32768; the complete signed16
identity adds `(n==INT16_MIN)`. Keep the old persistent pulse and mean, original
noise, phase, prior raw noise and all 160 RNG steps. Zero pulse gain is not silence.

Both helpers are portable C, with no new ASM, table or RAM field. Exhaustive
AVR scalar runs cover 196607 ABI/r1 returns per backend; ASM-enable 1/0 images
are byte-identical. Generic/bounded helpers take 23..24 / 12..13 cycles including
RET, 0 MULs. The isolated C original takes 147..150 / 4 MULs, which is not the
production inline ASM cost. Full C decoders compile/link only.

Complete NB2.15/WB3.95 speech CPU improves 31.904% ->31.791% / 69.474% ->69.388%.
Cost: 100/132 B Flash and 2 B NB stack, unchanged static RAM/WB stack. A common
WB prefold loop saves 78 B versus duplicated branches for 3.24 extra mean cycles
on the 384-frame layout screen. Nonzero WB frames cost at most 4 extra cycles
against baseline; zero frames save 876..927. Full raw, +8/+11% IRQ and scheduled
SPI retain exact PCM/PWM and no underruns. State tests add explicit nonzero
prior pulses at zero gain because that boundary is absent from the mixed corpus.
Target/toolchain/ABI are those above; benefits are only measured for this build.

[Bounded and general helpers](../../Codecs/Speex/AVR/src/nb1_zero_gain.h),
[complete evidence and reproduction](../../Codecs/Speex/AVR/WB_ZERO_GAIN.md).

## Specialize a proven zero context without clearing its incoming cursor

For prepared NB1 contexts only, previous[0]==0 proves all previous words and
both new pulses zero. The arithmetic proof covers the complete bounded domain;
the pinned 32 packet scales start at 16384, so current packets reach this path
only at gain 0. Keep the general arbitrary-table entry unchanged in meaning.

A separate zero ASM entry shares the existing prologue/epilogue via a short-
lived T selector through flag-neutral setup. Consume incoming pulse-minus-noise
on sample0, then omit previous-table and pulse work. Preserve mean, phase,
last class and RNG. Its explicitly selectable C equivalent uses the same
cursor/context interface; allocate no RAM flag. Architecture + explicit ASM
enablement remain necessary, independent of hardware memory reads.

On the target/toolchain above, 33255 vectors per backend compare general/zero
C/ASM and the selected path with the original recurrence. Zero ASM saves
517..526 cycles /84 SRAM bytes read per 40 words, with 160 mean MULs unchanged.
Complete WB3.95 speech CPU improves 69.388% ->69.222% for 188 B Flash; static and
peak RAM stay fixed. Ordinary frames cost 100 extra dispatch cycles, already
included. Full PCM, +8/+11% IRQ and scheduled SPI remain exact without underruns.
[Contract, measurements and scope](../../Codecs/Speex/AVR/WB_ZERO_SYNTHESIS.md).

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

```

Host checks cover all 65536 pulse amplitudes and all 65 gains. Retain bounds/casts
when adapting. Prepared dispatch inside ASM, finite pitch-root lookup and paired
opposite-noise prefold remain unmeasured candidates. Do not use completed innovation as prediction.
Measure compiled callers, stack and loaded IRQ/SPI before accepting them.
