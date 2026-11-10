# Narrow a division after proving its actual caller domain

Measured target: ATmega328P / classic AVR5, GNU ABI, AVR GCC 7.3.0,
avr8js 0.21.1. This entry covers isolated scalar execution, ABI and IRQ
checks. Whole-decoder throughput, PWM queues, transport and physical-board
operation require their separate integration gate.

The [complete HB1 response proof](speex-finite-lpc-response.md) bounds the
positive high-band response to `111..31849`, including reset's zero-coefficient
response 8274. Each signed16 difference and running response prefix also fits
signed16. This stronger result is specific to the pinned HB1 codebooks,
interpolation, margin repair and exact LPC conversion; it does not narrow the
existing generic ratio API's arbitrary-coefficient domain.

Keep two private contracts in [the helper header](../../Codecs/Speex/AVR/src/wb_gain_div.h):

- `speex_wb_ratio_div(low, high)` retains the original wider divisor domain,
  including the signed16 cast before the half-divisor shift.
- `speex_wb_ratio_hb_div(int32_t low, int16_t high)` accepts validated HB1
  responses only: `1 <= low <= 335949`, `111 <= high <= 31849`.

For the latter, `n = low*128 + (high>>1)` is strictly positive and lies in
`183..43017396`. The signed16 half-divisor cast is now exact because `high`
is positive signed16. Division therefore needs neither a negative-numerator
path nor a wide remainder. If `r = n>>15` is at least the divisor, the quotient
is at least 32768 and saturation returns 32767. Otherwise compute fifteen
quotient bits. At each step `r < high`, so `2*r+bit <= 63697` fits unsigned16.
The separate C helper preserves the same rounding, division and saturation.

The [GNU AVR leaf](../../Codecs/Speex/AVR/src/wb_gain_div.S) uses the narrower
ABI: numerator in r22..25, divisor in r20:21, result in r24:25. It preserves
r1 and all callee-saved registers, has no memory accesses, local stack,
persistent state or interrupt masking. Each function has its own text section;
section garbage collection removes the unused generic entry. The original
generic leaf remains 72 B and its instruction bytes are unchanged.

The fifteen steps use an inverted quotient. The unsaturated comparison leaves
carry set. A failed `CP/CPC` comparison retains carry one; successful `SUB/SBC`
leaves carry zero. The next `ROL` consumes that inverse quotient bit, avoiding
the conditional `ORI 1`. A final quotient `ROL` pair and `COM` pair restore
the positive result; initial carry one provides its zero sign bit. Instructions
between steps must preserve carry. The fully unrolled leaf has no loop-control
instructions; smaller DEC/BRNE recipes were screened separately. GNU macros
and `.rept` keep the source compact while emitting the measured unrolled code.

| Isolated recipe | Leaf bytes | Mean scalar caller cycles saved per captured frame |
| --- | ---: | ---: |
| Original generic 24-bit remainder | 72 | 0 |
| Generic-compatible 16-bit fast branch, rolling | 116 | 133.16 |
| Generic-compatible 3-step unroll, inverted quotient | 158 | 258.35 |
| Generic-compatible 15-step unroll, inverted quotient | 372 | 310.21 |
| Validated HB1, 15-step unroll, inverted quotient, narrower ABI | 306 | 370.21 |

These are paired scalar-wrapper measurements on the same 15076 arguments,
captured from 3769 frames across five WB profiles: 1152 frames each for
WB3.95/5.75/7.75, 249 for WB9.8 and 64 for WB12.8. They are summed scalar
costs per source frame, not a measured whole-decoder speedup. The final leaf
takes `138 + popcount(quotient)` cycles, or 138..153; saturation takes 16.
All include RET, excluding caller setup and IRQ entry/instructions. The selected
wrapper adds 54 cycles versus the generic wrapper's 62. No final firmware-size
claim follows from the 234 B difference between the two leaf sizes.

The retained full divisor sweep checks 106727 pairs: all 31739 divisors with
three low responses, 1510 boundary cases and 10000 coefficient-derived pairs.
This exhausts the divisor range, not every pair in the response rectangle.
Independent BigInt and isolated AVR C agree; 213454 ASM returns preserve
arbitrary callee-saved patterns and r1. Timer2 completes all 304939 compare
events/interrupts with its independent multiplication accumulator intact.
Fixture stack peaks at 22 B, including callers and ISR; leaf-local stack is zero.
Explicit C and forced-generic fixtures each pass 1862 IRQ cases and have
identical binaries. The unchanged wider generic API separately passes 4403
IRQ cases, including negative rounded numerators. No complete C decoder runs.

The [receipt](../../Codecs/Speex/AVR/reports/wb-hb-ratio-unit.json) explicitly
reuses the original full scalar result after the complete promoted fixture
rebuilds byte-identically. Named quick checks and argument replay are fresh.
Source hashes normalize UTF-8 text to LF; external compiler/subtool and device
header hashes retain exact bytes. Both replay timing arrays are hashed and
decoded as little-endian uint16 pairs; exact length and raw/selected totals
are checked against the recorded scalar statistics. Arithmetic selection still
requires the existing supported architecture/ABI checks and explicit ASM enable; disabled
ASM or an unmatched architecture selects C, including on AVR itself.

Reproduce independent scalar checks in a fresh output directory, keeping the
retained evidence directory intact:

```sh
python Codecs/Speex/AVR/tests/build_wb_hb_ratio.py --avr-gcc avr-gcc --out Codecs/Speex/AVR/build/hb-ratio-reproduce
node Codecs/Speex/AVR/tests/verify_wb_hb_ratio.mjs Codecs/Speex/AVR/build/hb-ratio-reproduce/asm --irq
node Codecs/Speex/AVR/tests/verify_wb_hb_ratio.mjs Codecs/Speex/AVR/build/hb-ratio-reproduce/asm --quick --irq
node Codecs/Speex/AVR/tests/verify_wb_hb_ratio.mjs Codecs/Speex/AVR/build/hb-ratio-reproduce/c --quick --irq
node Codecs/Speex/AVR/tests/verify_wb_hb_ratio.mjs Codecs/Speex/AVR/build/hb-ratio-reproduce/generic --quick --irq
node Codecs/Speex/AVR/tests/verify_wb_ratio.mjs Codecs/Speex/AVR/build/hb-ratio-reproduce/generic-control --quick --irq
```

[Capture](../../Codecs/Speex/AVR/tests/capture_wb_hb_ratio.mjs) accepts
`--firmware`, `--streams`, `--oracle`, `--out` and optional `--frames`.
It rejects C firmware, checks every PCM/reset result and supports both scalar
ABIs. It writes argument JSON only to the requested output, leaving input
firmware untouched. Replay that JSON with `verify_wb_hb_ratio.mjs UNIT_DIR
--irq --replay CAPTURE.json`; use both the `asm` and `generic-control` fixtures
for a matched comparison. Captures and generated binaries remain ignored.

`python Codecs/Speex/AVR/tests/audit_wb_hb_ratio.py --check` verifies the retained
receipt against its local `build/wb-hb-ratio-unit/` reference/replay evidence.
That audit needs the preserved evidence pack; compiling a fresh standalone
fixture does not recreate historical captures or the parent generic image.
For an archived isolated candidate, `--adopt-candidate PATH` first requires
identical complete fixture binaries before copying its full scalar result and
reference pack. It does not rerun or relabel historical results as fresh.

## Count repeated rounds when Flash is the priority

The 2026-11-10 size recipe replaces fifteen expanded inverse-quotient rounds
with one round, `LDI r18,15`, `DEC r18` and `BRNE`. Both loop instructions
preserve C, which carries the inverse quotient bit into the next `ROL`.
The shorter function also permits a direct saturation branch. Do not insert
an instruction that changes C between a round and the next rotation.

On the same ATmega328P/GNU ABI/AVR GCC 7.3.0 target, the leaf shrinks from
306 to 58 B. An unsaturated call costs exactly 44 more cycles; a saturated
call saves one. Local stack and static SRAM remain zero. The separately
selectable C equivalent and the wider generic API are unchanged.

The [size receipt](../../Codecs/Speex/AVR/reports/wb-ratio-size-unit.json)
records a fresh 106727-pair scalar sweep, all 31739 valid divisors, 213454 ASM
returns and 327285 completed Timer2 interrupts. Explicit C and forced-generic
selection each pass 1862 IRQ cases. A matched replay of 15076 actual calls
checks both raw-leaf and selected-wrapper timing deltas; the complete wider
generic control fixture remains byte-identical.

A whole-image WB9.8/WB12.8 screen covers 249/64 frames respectively: decoder
Flash is 26164 -> 25916 B, PCM/reset/PWM is exact, static SRAM and peak stack
are unchanged, and +8% foreground-load IRQ output has no underruns. Minimum
queues stay 7/8 and free SRAM stays 398/391 B. Added decoder work is at most
176 cycles/frame (0.055% of the 320000-cycle frame budget). This is a bounded
screen, not a fresh full-corpus or physical-board admission.

Rebuild and run the scalar commands above in `build/ratio-size`, replay the
retained `wb-hb-ratio-unit/replay/actual-all.json`, and use
`tests/audit_wb_ratio_size.py --reference PATH_TO_ADMITTED_wb-hb-ratio-unit`.
The audit also binds the whole screen under `build/ratio-size/whole` to its
admitted `hb-finite-speed` baseline. Historical stage receipts describe their
pinned sources; changing production later does not relabel those measurements.

The finite-domain specialization, inverted quotient and measured recipes are
original project work. Preserve the surrounding [Xiph fixed-point semantics](../../Codecs/Speex/AVR/vendor/speex-1.2.1/libspeex/fixed_generic.h)
and [Speex 1.2.1 BSD notice](../../Codecs/Speex/AVR/vendor/speex-1.2.1/COPYING).
