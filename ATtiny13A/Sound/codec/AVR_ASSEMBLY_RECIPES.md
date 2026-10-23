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
