# Exact C decoding on ATmega328P

The universal v9 fixed-point C decoder now meets the tested 8 kHz playback
deadline on ATmega328P at 16 MHz. No compressed byte or decoded fixed-point
sample changes. This is C source compiled for real AVR5 hardware multiplication,
with `LPX4_ENABLE_ASM=0`, `LPX4_FLOAT_SYNTHESIS=0`, AVR-GCC 7.3.0, `-Os -flto
-mcall-prologues -mrelax -finline-small-functions`, FIFO 32/prefill 24, SRAM512
layout and two LPC segments. The complete compiler options are in the receipt.

| Public workload | C cycles/sample including IRQ | Program excluding audio |
| --- | ---: | ---: |
| Chego, about 2 kbit/s | 1779.025 | 4895 B / 4.780 KiB |
| Chego P4 | 1810.367 | 4894 B / 4.779 KiB |
| Chego P6 | 1815.062 | 4894 B / 4.779 KiB |
| Changing sparse80, extreme filters | 1860.555 | 4895 B / 4.780 KiB |

Chego previously needed 2341.106 cycles/sample and underrun the queue. The new
result is about 24% lower; program Flash grows from 4815 to 4895 B (+80 B,
1.66%). Its 297 B of audio is unchanged, giving a 5192 B / 5.070 KiB complete
image. Static RAM is 433 B and observed stack is 75 B. IRQ is the safe ordinary
64-cycle C handler, including hardware entry and complete RETI. Mean decoder
CPU plus the full IRQ excludes foreground queue management, and is not a
per-call worst-case bound. All four full playbacks have exact PWM and no
underruns in native simavr 1.6; no physical board was measured.

## Reusable C techniques

For a signed32 value, write `v = 65536*h + l`, with signed16 high word `h`
and unsigned16 low word `l`. Then

```c
floor(v / 4096)  = 16*h + (l >> 12);
floor(v / 16384) =  4*h + (l >> 14);
```

The products by 16/4 and final sums fit signed32 even at its endpoints. Use
multiplication, not a signed left shift of negative `h`. GCC can move words
and shift narrow operands instead of performing twelve/fourteen four-byte
arithmetic shifts. The supported compilers retain the existing two's-complement
signed-shift behavior; the test reference independently uses signed64 division
with mathematical floor semantics.

For bounded Q14 attenuation, coefficient is 0..16384 and state is signed16.
The result fits signed16, so only product bits 14..29 matter. Form the exact
signed32 product, convert to unsigned32, shift left twice modulo 2^32 and
extract its high word. This avoids a long signed32 right shift. Do not apply
this truncation to an unrestricted result that needs more than sixteen bits.

PWM can similarly add its rounding bias and output offset *before* extraction:
`biased = sample*gain + 8192 + 128*16384`. An unsigned comparison against
`256*16384` detects both clipping directions; the original sample sign selects
the endpoint. For an in-range result, only bits 14..21 are needed: extract a
sixteen-bit window first, then shift it six bits. All products and signed sums
fit signed32 over every signed16 sample and unsigned8 gain.

Existing handwritten AVR5 and AVR25 branches stay selected only through their
real architecture definitions and explicit ASM-enable key. The AVR25 MulQ14
fallback deliberately keeps its previous expression; applying the new C helper
there would change the existing no-MUL ASM image. The C fallback remains
selectable on both AVR targets and hosts, independently of Flash access.

## Validation and retained history

The [fresh eight-case IRQ receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/c-realtime-measurements.json)
contains four C and four ASM runs. The [current arithmetic receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/c-realtime-math-measurements.json)
has 600,435 independent cases per C/ASM/generic AVR backend with active IRQs.
The additional native UBSan test checks 2,983,059 shift inputs, two million
full Q14 products, 1,703,936 bounded attenuations, and all 16,777,216 sample/gain
pairs. It uses an independent division-based reference.

The [anonymous complete corpus](../../Codecs/LPX/research/c-fixed-realtime-2026-11-10/corpus.json)
covers all 181 recordings / 306 baseline-v9 sparse80 segments / 15,188,029
samples. Every old native, new native and actual PWM stream is identical;
there are zero underruns and failures. Maximum mean CPU plus IRQ is
1810.873220 cycles/sample and minimum queue is 15. This corpus is profile15;
P4/P6 and the more expensive synthetic control are covered separately above.
Twenty stress images exceed the historical 6.5 KiB complete-image preference
(maximum 6818 B), while the decoder program stays at most 4895 B. The target
here is the Mega's 32 KiB physical Flash; this does not admit those images to
the older Tiny88 bootloader budget. Media, identities and private media hashes
are not retained in the anonymous report.

The source-frozen corpus predates adding the optional double selector. All
four corresponding final default-0 C images are byte-identical to that frozen
candidate. The [explicit source transition](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/c-numeric-transition.json)
records this separately. It also preserves original receipt/catalog hashes
from `393b2de2`; old timing values are never rebound to changed source.
All 18 current fixed ASM website images rebuild to exactly the shipped HEX
bytes, with no float runtime linked. Those identical images reuse their
existing IRQ evidence; no fresh website IRQ run is claimed.

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_atmega328p_v9.py \
  build/current-c --current-source --wsl Ubuntu
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_fixed_c_math.py
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_web_asm_equivalence.py \
  build/asm-equivalence --run --wsl Ubuntu
```

Use fresh ignored output directories; omit `--wsl Ubuntu` on Linux. Floating
desktop synthesis is a separate build selection, described in
[FLOAT_SYNTHESIS.md](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/FLOAT_SYNTHESIS.md).
It intentionally retains fractional state and is not the bit-exact AVR oracle.
These are original project C transformations, not adapted third-party code.
