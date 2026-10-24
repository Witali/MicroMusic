# AVR assembly sources and their use in the speech decoder

Checked 2026-10-23. The runtime remains handwritten assembly in
[`fixed/firmware.S`](fixed/firmware.S). Python is the independent integer
specification and the automatic encoder; GCC assembles and links the AVR source.

## Primary references

| Reference | Useful material | Application here |
| --- | --- | --- |
| [Atmel AVR200 / AN0936](https://ww1.microchip.com/downloads/en/Appnotes/doc0936.pdf), [source-code download page](https://www.microchip.com/en-us/application-notes/an0936) | Software multiplication/division, separate size and speed implementations, shared input/result registers | Compare small shift/add loops with our bounded multipliers. The 8×8 unsigned size implementation is 9 words plus RET; the speed implementation is 34 words plus RET. Words are two bytes. |
| [Atmel AVR202](https://ww1.microchip.com/downloads/en/AppNotes/doc0937.pdf) | Carry chains for addition, subtraction, constants and comparisons | Keep 16-bit operations in register pairs; constant additions can use subtraction of the negated constant. |
| [AVR-LibC Inline Assembler Cookbook](https://avrdudes.github.io/avr-libc/avr-libc-user-manual/inline_asm.html) | Nibble/byte swaps, register constraints, memory access and branching | Useful instruction idioms. Its inline-assembly constraints matter when embedding snippets in C; our standalone source has its own register convention. |
| [AVR-LibC and Assembler Programs](https://avrdudes.github.io/avr-libc/avr-libc-user-manual/assembler.html) | Complete assembly modules, symbols, sections and interrupt examples | Relevant companion to the inline cookbook for this project. |
| [Atmel AVR001 / AN2550](https://ww1.microchip.com/downloads/en/AppNotes/doc2550.pdf) | Conditional assembly and peripheral-access macros | Select target features while assembling, avoiding runtime tests where a model or MCU fixes the choice. Its original assembler syntax must be adapted to GNU AVR assembler. |
| [Microchip AVR Instruction Set Manual](https://ww1.microchip.com/downloads/en/devicedoc/AVR-Instruction-Set-Manual-DS40002198A.pdf), [ATtiny13 device manual](https://ww1.microchip.com/downloads/en/DeviceDoc/doc2535.pdf) | Flags, cycles, operand restrictions and available instructions | Validate every borrowed idiom for this device. ATtiny13 has ADIW/SBIW, but no hardware MUL. Emulator support and hardware support are separate questions. |

No third-party source archive is copied into this repository. The routines are
design references; exact ranges, rounding and available instructions determine
whether an implementation can replace ours.

## Recipe: unrolled small multiplication from our music firmware

Source: [`Alicia render_tone, .L25c`](../../Music/variants/alicia/synth.S),
generated from [`tools/alicia-native-template.S`](../../../tools/alicia-native-template.S).
This is the existing music routine identified by the user, not a newly invented
general multiplier. It evaluates the gain bits from most to least significant
using Horner's rule: double the partial result, then conditionally add the
original sample. Unrolling removes the loop counter and backward branch.

```asm
/* Input r17: signed wave -8..7; r25: unsigned gain 0..15.
 * Output r17 = floor(wave*gain/4). Clobbers r0, r17, SREG; preserves r25.
 * All intermediate products fit signed 8 bits within these exact bounds. */
 mov r0, r17
 sbrs r25, 3
 clr r17
 lsl r17
 sbrc r25, 2
 add r17, r0
 lsl r17
 sbrc r25, 1
 add r17, r0
 lsl r17
 sbrc r25, 0
 add r17, r0
 asr r17
 asr r17
 ret
```

The actual extracted source assembles to **15 words / 30 bytes including RET**.
All **2304** in-domain cases (16 samples × 16 gains × 3 initial flag states
× 3 engines) match independent integer arithmetic. The isolated body takes
**18 cycles including RET**, or 21 cycles with one RCALL. This excludes waveform
lookup, surrounding synthesis and interrupt costs. Each skip covers exactly
one single-word instruction, so these conditional pairs have equal timing.
The measured [report](../research/avr-music-scale/report.json) fingerprints both
the original source and extracted binary. Reproduce it with:

```text
python tools/probe-avr-music-scale.py --avr-bin <AVR-bin> --node <Node-executable>
```

The reusable idea is the bounded, unrolled shift/add structure. Copying this
8-bit body into the speech lattice is incorrect: for sample 100 and gain 15 it
wraps and returns −9 instead of 375 after scaling. The probe executes this
counterexample in all three engines as well. Speech needs a wide intermediate,
the existing signed-byte NEG convention (including −128), and the appropriate
Q3/Q7 rounding rule. Use ADD/ADC and LSL/ROL pairs or another proven wide
product implementation. Unrolling can also increase Flash and slow small
coefficients compared with repeated addition; compare the complete player and
data budget before selecting it. Our subsequent Kmap experiment measures
unrolled Q7 separately from the smaller stage-selected Q3/Q7 implementation.

### Keep the cheaper arithmetic for stages that do not need more precision

Our [Kmap lattice](q3-kmap/README.md) needs Q7 only for K1/K2. The existing
stage counter selects Q7 for those two stages and retains the small Q3 product
for the other six. The sample, sign handling and rounding rules stay identical
to the independent oracle; storage precision alone is not a reason to run the
more expensive multiplier everywhere.

In the measured floor profiles, stage selection uses **458 code bytes** versus
**470** for unrolled Q7 throughout. On the same edge-test stream/table the
minimum timing margins are **204** and **117 cycles**, respectively. The
nearest variants use 464/474 code bytes and 186/84 cycles of margin. These are
complete fixture measurements, not isolated multiply latencies or a universal
upper bound for arbitrary speech parameters. Every fitted phrase still needs
its own timing verification. The selected full quality-study phrase has 135
cycles of slack at 1022 Flash + 64 EEPROM bytes.

A second comparison uses the same 550-byte full-phrase stream and EEPROM for
both profiles: stage-selected 1010 Flash bytes / 136 cycles of slack versus
unrolled 1022 / 114. All 66,816 phrase-and-silence samples are identical in all
three engines. The literal three-bit, 16-bit Horner adaptation also has a
measured cost: **24 additional code bytes**. At coefficient magnitude 1 the
old loop takes 26–27 cycles and Horner 38–39; at magnitude 7 the loop takes 56–57
and Horner 38–39. Those routine timings include RET; add 3 for RCALL. The
[reproducible benchmark](../research/q3-kmap-avr-qualification/music-unroll.json)
contains 92,160 arithmetic checks for the literal adaptation. These isolated
checks do not establish a complete-player deadline for that larger variant.

The practical rule is to measure both branches: a loop-free small product is
useful, but preserving a cheap specialized path can save both bytes and cycles.
The [qualification report](../research/q3-kmap-avr-qualification/report.json)
records 829,440 exhaustive product cases in three engines and the source hashes.

## Recipe: spend unused registers before saving them on the IRQ stack

In the whole-program ordinary Q3 player, frame-mode bits can move from high
register r22 to unused r14. Reserve r22 for the IRQ countdown and r12 for SREG.
Startup initializes r22 to five; the main loop must leave both registers alone.
Nested IRQs are disabled.
The handler then needs no PUSH/POP scratch-register preservation:

```asm
irq:
 in r12, SREG
 dec r22
 brne irq_end
 ldi r22, 5
 tst r8
 breq irq_end
 out OCR0B, r7
 clr r8
irq_end:
 out SREG, r12
 reti
```

Against our previous handler, this saves **12 complete-player bytes** including
initialization and reload changes. The measured maximum handler length falls
from **28 to 19 cycles**, and stack high-water use from **6 to 4 bytes**. This
requires auditing every writer of r12/r22; it is not a C calling-convention rule.
The real routine passes **1,536** flag/countdown/ready cases across three engines,
checking all other registers, SREG/T, output, return and stack.

## Recipe: move an exact scale into an existing constant table

Our excitation computes `tap*gain`, with signed tap −7…7 and gain 0…15, using
the lattice's wide Q3 multiplier. Instead of shifting gain left three times
for every lookup, store `tap*8` in EEPROM and exchange the multiply operands:

```asm
 in r21, 0x1d     /* EEPROM data: signed tap*8, within -56..56 */
 mov r23, r3      /* nonnegative gain 0..15 */
 rcall mul_q3     /* floor((tap*8)*gain/8) = tap*gain */
 mov r18, r24
```

This removes **three instructions / six code bytes**, while retaining the same
64 EEPROM bytes and exact PCM. Products stay within ±840; neither negated
sample nor intermediate width reaches an unsupported boundary. It can take
more multiply iterations because the coefficient is now gain, so qualify
complete-player timing. The actual path passes **9,216** address/gain/flag
cases across three engines. Firmware and its scaled EEPROM image form one pair.

Two additional whole-program invariants save another **six bytes**: YH remains
zero after initialization, so its reader CLR is redundant (two bytes); reset
CLI/CLT fit the unused words before the Timer0 vector (four bytes). Reset must
enter address zero, and additional enabled interrupt vectors need a new layout.

Together, these four measured steps reduce **392 → 368 core bytes**, with the
same full Vinni sound at **990 Flash + 64 EEPROM** instead of 1014 + 64. The
final minimum preparation slack is **352 cycles**, versus 332 before. These
figures apply to the ordinary floor profile and measured streams. The eight
full builds, expanded 655-byte stream capacity and reproducible guarded source
transformations are retained in the [compaction study](../research/q3-core-compaction/README.md).

## Recipe: shorten zero pulse tails and budget the complete reader

The retained four-by-sixteen Vinni pulsebook has only four active taps per
row. A compile-time width of four removes zero tails exactly. Reject a shorter
width whenever any removed tap is nonzero; keep the original logical book and
integer decoder as the oracle.

| Physical table | Waveform EEPROM | Speech prefix EEPROM | Core | Full Flash |
| --- | ---: | ---: | ---: | ---: |
| Sixteen scaled bytes per row | 64 | 0 | 368 | 990 |
| Four scaled bytes per row | 16 | 48 | 398 | 972 |
| Four signed nibbles per row | 8 | 56 | 410 | 976 |

Signed nibbles are exact here, but byte taps win the complete budget: the extra
eight prefix bytes do not repay twelve extra code bytes. Byte taps retain the
previous `tap*8` encoding. Signed two's-complement nibble taps unpack directly
to the same scale:

```asm
/* C = original lag bit 0, preserved through address logic and the IRQ. */
 in r21, 0x1d
 brcs pulse_high_nibble
 swap r21
pulse_high_nibble:
 andi r21, 240
 asr r21                 /* signed tap*8 */
```

The extra source bytes are useful because a shared **26-byte stream reader**
can consume an EEPROM prefix before switching Z to the Flash suffix. All five
stream-read sites call it. Advance the prefix pointer after reading the byte;
when it reaches the compiled boundary, load the Flash pointer before returning.
This keeps splits inside headers/coefficient packets transparent. EOF remains
in Flash, and SREG.T remains available for the original one-shot stop rule.

The net saving is **18 Flash bytes**: 48 speech bytes moved to EEPROM minus
30 added code bytes (short addressing plus reader). The 620-byte stream fits
at **972 Flash + 64 EEPROM**, and the physical stream capacity rises **655 →
673 bytes**. The phrase has 208 cycles of slack instead of 352, so qualify every
new fitted stream. Firmware and its EEPROM image must be programmed together.

Widths 4/8/16, byte/nibble encodings, IRQ carry preservation, zero-tail bypass,
short prefixes and actual 1024-byte maximum images are checked. See the
[eleven-variant study and qualification](../research/q3-short-eeprom/README.md)
for the automatic whole-image selection and reproduction commands. The PCM,
duration and quality metrics are unchanged.

## Recipe: extend a selector through an unused packet bit

When a compact stream has no free bits in its common spectral byte, check its
extended header before reducing gain precision or adding an unconditional byte.
The Q3 header has an unused bit 2 in the `0xc0..0xc3` duration escape. It can hold
the third waveform bit, selecting eight forms while retaining **all sixteen gains**.
Selectors 0–3 keep their original bytes. Selectors 4–7 force an extended header
only when the frame did not already require one; the actual packer must charge
this extra byte during fitting. Tag the extension as a separate format and reject
unknown header bits in the portable reader.

The eight-form four-tap nibble decoder clears the upper address in R13 at every
frame, then captures it from extended headers:

```asm
vbr_pitch:
 clr r13
 /* compact-header parser or branch to vbr_extended */
vbr_extended:
 mov r23, r16
 andi r23, 4
 lsl r23                  /* four rows * two bytes per row = eight */
 mov r13, r23
 /* existing extended pitch/duration parser */
```

At the lookup, OR the upper base into the address after forming its low bits.
`OR` preserves carry, needed for the packed odd/even tap. The IRQ must preserve
both the carry and R13. Clearing R13 only for extended headers is insufficient:
a later compact header could otherwise retain an upper selector.

The real core grows **410 → 422 bytes** relative to four-form nibble storage.
Eight four-tap forms occupy **16 EEPROM bytes**, leaving **48 speech bytes**.
The same-PCM control is 996 Flash; the fitted Vinni image is **1012 Flash +
64 EEPROM**, with **199 cycles** of preparation slack. The 649-byte stream limit
is checked with a complete 1024-byte build. Header, gain and IRQ lookup checks
cover **73,728 cases** in three engines. See the
[eight-form study](../research/q3-pulsebook8/README.md) for evidence and limits.

Before spending header bytes, recode exact duplicate rows to the cheapest lower
index, and zero the inaudible selector on unvoiced/zero-gain frames. Keep the gain
and all decoder state rules. Equality of the full PCM and all four wrap counters
proves this recoding for the input stream. It freed **five bytes** in the first
fit, without adding any AVR instructions. This storage optimization alone does
not improve sound; further fitting uses the freed budget.

## Recipe: store only reachable waveform rows

The maximum selector space can be a power of two without reserving that many
physical EEPROM rows for each recording. Canonicalize duplicate rows, set the
selector to zero on unvoiced/zero-gain frames, and collect the rows used by voiced
nonzero-gain frames. Reindex them consecutively and retain one zero row when
there are no active forms. Keep a full logical table on the PC as the oracle.

Assign the first four indices by how often they avoid forcing an extended
header, rather than by tap values or row number. Then select width, byte/nibble
storage and decoder together. Four or fewer forms need no upper-selector parser;
the existing four-form ASM is sufficient. The EEPROM speech prefix starts
immediately after the last stored row. A non-power-of-two table needs no extra
AVR dispatch or bounds instructions when all reachable indices are proven.

For four-tap forms, the complete-image choices are:

| Stored forms | Physical taps | Waveform EEPROM | Speech prefix | Core | Stream capacity |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | scaled bytes | 4 | 60 | 398 | 685 |
| 4 | scaled bytes | 16 | 48 | 398 | 673 |
| 5 | scaled bytes | 20 | 44 | 412 | 655 |
| 6 | signed nibbles | 12 | 52 | 422 | 653 |
| 7 | signed nibbles | 14 | 50 | 422 | 651 |
| 8 | signed nibbles | 16 | 48 | 422 | 649 |

Five forms tie in total size between byte and nibble storage; the smaller,
faster byte decoder wins the tie. Re-evaluate this decision whenever width,
prefix or stream changes. Unused space is useful only if code plus data plus
EOF/alignment is smaller after rebuilding the whole image.

The seven-form Vinni control saves **1012 → 1010 Flash bytes**, with the same
PCM, **64 EEPROM**, **199 cycles** of slack and **28 bytes** maximum SRAM span.
Actual builds test zero through eight active forms, and one/seven-form maximum
streams execute at exactly 1024 Flash bytes. The portable packer preserves the
whole PCM and all wrap counters. Generated Flash and EEPROM remain one pair.

## Recipe: extract a high flag into a low register through carry

An extended pitch byte holds a seven-bit integer period and a high fraction
flag. Saving the original, masking twice and copying into low registers takes
seven words. This six-word sequence retains both fields:

```asm
 lsl r16                 /* high fraction flag -> C; period shifts left */
 clr r9                  /* preserves C; IRQ must preserve SREG and r9 */
 rol r9                  /* fraction flag -> r9 bit 0 */
 lsr r16                 /* original seven-bit period */
 mov r4,r16
 mov r2,r16
```

Keep the cycle's extra-sample toggle in R9 bit 1, separate from the enable bit.
Toggle with `EOR` against 2, not an increment that could eventually carry into
the enable bit. Adjust both the phase reload and waveform lag on extra-sample
cycles; otherwise the first tap would be repeated. Clear both bits on each
frame load, including noise/integer frames. SREG.T remains the one-shot flag.

The complete half-pitch extension measures **24 added bytes** after this
two-byte saving. The selected four-form Vinni is **1022 Flash + 64 EEPROM**,
with **202 cycles** minimum preparation slack and unchanged PCM versus the
previous 1024-byte image. Four targeted contracts include rapid period-one
alternation beyond 128 toggles, eight-form mixed packets and full phrases in
three engines. The [half-pitch study](../research/q3-adaptive/README.md) retains
the measured spectral/intelligibility changes, complete images and limits.

## Recipe: compact signed word multiplication by a fractional nibble

[`word-q4/multiply.S`](word-q4/multiply.S) supplies Q4 and Q5 entry points in
**72 bytes total**, sharing the body. Input is signed `r19:r18`, coefficient
is preserved in `r20`, and output is `r25:r24`. It also preserves `r16:r17`,
pointer registers and SREG.T/I; `r27` must be zero. It implements symmetric
nearest rounding, with ties away from zero, rather than the old floor profile.

After the coefficient's sign handling, form an unsigned magnitude up to 32768.
Starting with a zero accumulator, consume coefficient bits from low to high:
add the magnitude when the bit is one, then shift the accumulator right once.
Four steps give `floor(magnitude*coefficient/16)`. The accumulator is always
less than the magnitude before the next addition, so their sum fits unsigned
16 bits. No 24-bit product or shifted multiplicand is needed. The last ROR's
carry is the half-bit for rounding; DEC/BRNE preserve it. Round the magnitude,
then restore its sign. The Q5 entry uses five steps and can also handle the
half-unit waveform/gain product with an appropriate fixed input scale.

The initial coefficient-sign negation wraps as a 16-bit operation, including
`-32768`, matching the guarded PC decoder exactly. The subsequent absolute
magnitude uses unsigned 32768. This avoids silently changing that corner case.

The [retained isolated proof](../research/word-q4/multiplier.json) checks
**6,147,462 scalar calls** in three AVR engines. Q4 exhausts every signed
16-bit input with coefficients -15..15. Q5 covers boundary/strided words, all
coefficients and every physical tap/gain pair. An additional **192 IRQ cases**
interrupt between the final ROR and ADC, checking carry, SREG.T/I, caller
registers and stack restoration. Both Q4/Q5 routines occupy 72 bytes together;
the complete fixture with vectors and IRQ is 104 bytes.

Measured entry-through-RET bounds are **13–66 cycles for Q4** and **11–73 for Q5**,
excluding the caller's RCALL. A complete lattice uses fifteen word products
per sample, plus excitation, parsing, output and interrupt work. These isolated
figures do not prove the full decoder's deadline, SRAM bound or 1024-byte fit.
`probe-word-q4-mul.py` defaults to exhaustive Q4 verification; its `--quick`
profile is used by the ordinary test suite to avoid repeating millions of calls.

## Factor initial zero bits in the small coefficient

[`word-q4/multiply-factored.S`](word-q4/multiply-factored.S) implements the
same signed Q4/Q5 ABI and symmetric rounding as the compact multiplier.
Before the first set coefficient bit, the accumulator is zero: skip its word
shifts and reduce the remaining division count. Copy the first nonzero term
instead of adding to zero. For powers of two, finish with a shift-only loop.
DEC, branches and the final jump preserve the last rounding carry.

The profile costs **106 rather than 72 bytes**. It passed **6 147 462** scalar
checks plus **192 IRQ cases** in three engines. Worst scalar time improves
only **66 → 65** Q4 cycles, but common small coefficients benefit more: the
complete six-fraction-bit Q4 teacher drops **1218 → 1178 cycles** per worst
filter call with identical PCM and every state. Arithmetic grows **180 → 214
bytes**. This remains an optional tradeoff, not a complete-player deadline
or a proven total-size win. Reports: [scalar](../research/word-q4/multiplier-factored.json),
[full filter](../research/word-q4/filter-six-factored.json).

## A word lattice with descending Flash coefficients

[`word-q4/filter.S`](word-q4/filter.S) keeps eight little-endian word states
and the deemphasis history in **18 SRAM bytes**. Y walks the states backwards;
Z reads signed Q4 coefficients directly from Flash. The top stage needs one
multiply, the remaining seven need two. Preserving the old state in r17:r16
across the shared multiplier avoids temporary SRAM writes. The same source
supports four or six state fraction bits; only the final arithmetic shifts change.

The assembled arithmetic occupies **172 / 180 bytes**, including the shared
72-byte multiplier. Complete retained phrases match all three engines, every
word state and the PWM output, with an IRQ injected between the final ROR and
rounding ADC. The four-bit cases take up to **1212 cycles**, the six-bit Q4
teacher up to **1218**, excluding the outer RCALL, excitation and frame parsing.
The eight-byte observed stack includes outer/inner calls and the synthetic IRQ.
This is insufficient slack to claim a complete 7500 Hz player: optimize the
multiply/stage schedule or test fewer stages before attempting selection.

Reproduce with `tools/test-word-q4-filter.py`. The input generator checks each
model's state precision and coefficient profile rather than silently running
Q7 controls through a Q4 kernel. Reports: [four-bit](../research/word-q4/filter.json),
[six-bit](../research/word-q4/filter-six.json). This is an arithmetic fixture;
the host supplies decoded excitation and coefficient transport.

## Changes that preserve the decoded bytes

- **Round using the last discarded bit.** After a signed ASR/ROR loop, carry
  contains the rounding bit. DEC and BRNE preserve carry. ADC with the permanent
  zero register rounds the result, including low-byte overflow propagation.
  This removes the separate loop that constructs and adds a rounding constant.
  Negative halfway cases still round toward positive infinity.
- **Bias packed wave taps by eight.** The old Mini-LPC stores coefficients with
  an offset. Applying the same representation to the new AVR wave table permits
  ANDI/SWAP unpacking. Remove the constant offset once after interpolation,
  rather than sign-extending two nibbles with repeated ASR. Portable PF data
  retains signed nibbles; the AVR data packer performs this representation change.
- **Share the residual multiplier.** White and colored excitation enter one
  multiply path; only the final scale differs. This saves instructions without
  changing intermediate rounding.
- **Use a direct conditional branch where it reaches.** The changed-field reader
  branches directly into its bit reader. Long branches in the main sample loop
  use explicit local trampolines instead; AVR branch reach is checked by linking.

`tools/test-fixed-avr-kernels.py` extracts the actual source sections, assembles
fixtures that fit the real 1 KiB ROM, and compares their execution in JS and WASM
with independent expected integer results. This covers negative boundaries,
rounding, table wrap, phase, FIR, saturation, bit parsing and DC state. It does
not establish that the complete firmware fits or meets every sample deadline.

## Comparison with the previous Mini-LPC

The archived `release/chego/firmware.S` assembles to **406 bytes of code** plus
552 bytes of speech, a loop marker and alignment: **960 bytes total**.
Its excitation is a short pitch-triggered pulse or binary noise. An eight-stage
lattice filter uses eight byte coefficients and eight byte state values. The
coefficient multiplier performs repeated additions followed by an arithmetic
division by sixteen. The byte-aligned frame reader updates all coefficients,
either half, or none, with durations of 64–256 samples.

The new decoder models the actual period shape, preserves phase, interpolates
waves and frames, and adds colored residual noise and continuous DC removal.
Those additions account for much of its larger code size. The proven old timer
protocol is already reused: 37.5 kHz PWM, one output per five overflows, a ready
register and a small interrupt handler.

Useful further candidates are variable frame durations, bounded small-coefficient
multiplication and conditional omission of unused synthesis modes. Their *total*
code-plus-data cost must be measured: replacing the new bit stream with three
bytes per frame adds 202 bytes for the 144-frame example, enough to consume the
expected reader-code saving.

The old byte-state arithmetic wraps on overflow; adopting it would change the
sound. Its Q4 multiplier also is not a general replacement for a signed 16-bit
blend delta times a 6-bit fraction. AVR200's compact signed routine has a stated
extreme-negative-input limitation. Each candidate therefore needs boundary tests
before substitution. Restoring frame-wise phase resets would also discard an
audibly useful part of the new model.

## Approximate changes require measurement

`tools/probe-fixed-simplifications.py` and `tools/probe-fixed-rendering.py`
compare simplifications against the exact integer output, canonical original,
STOI/eSTOI and the existing spectral objective. FIR sharing and removal of a few
quiet unvoiced base frames can be compensated automatically. Reducing phase
precision or removing frame fades has a much greater measured cost. Keep those
experiments separate from instruction substitutions that preserve every byte.

The complete fixed decoder still exceeds ATtiny13 Flash. The builder reports
oversize explicitly and enforces the 1024-byte limit independently and in the
linker. A successful isolated arithmetic fixture is not a playable full image.
