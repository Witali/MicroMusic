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
 * All intermediate products fit signed8 bits within these exact bounds. */
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

The actual extracted source assembles to **15 words /30 bytes including RET**.
All **2304** in-domain cases (16 samples ×16 gains ×3 initial flag states
×3 engines) match independent integer arithmetic. The isolated body takes
**18 cycles including RET**, or21 cycles with one RCALL. This excludes waveform
lookup, surrounding synthesis and interrupt costs. Each skip covers exactly
one single-word instruction, so these conditional pairs have equal timing.
The measured [report](../research/avr-music-scale/report.json) fingerprints both
the original source and extracted binary. Reproduce it with:

```text
python tools/probe-avr-music-scale.py --avr-bin <AVR-bin> --node <Node-executable>
```

The reusable idea is the bounded, unrolled shift/add structure. Copying this
8-bit body into the speech lattice is incorrect: for sample100 and gain15 it
wraps and returns-9 instead of375 after scaling. The probe executes this
counterexample in all three engines as well. Speech needs a wide intermediate,
the existing signed-byte NEG convention (including-128), and the appropriate
Q3/Q7 rounding rule. Use ADD/ADC and LSL/ROL pairs or another proven wide
product implementation. Unrolling can also increase Flash and slow small
coefficients compared with repeated addition; compare the complete player and
data budget before selecting it. Our subsequent Kmap experiment measures
unrolled Q7 separately from the smaller stage-selected Q3/Q7 implementation.

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
