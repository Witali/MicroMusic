# LPX on AVR25 without MUL

The integration and size measurements below are retained as historical
evidence. The later [Tiny88 memory and Flash budget entry](lpx-tiny88-budget.md)
records fixed-ROM state removal, optional FIFO24 and the current full-player
checks. The current hard cap is **8192 bytes**, including audio; the former
6656-byte gate below is historical. Images above the MH-ET LIVE standard USB
bootloader's **6012-byte** application region require ISP loading. Speex is
excluded from the Tiny88 profile.

Measured on ATtiny88 / AVR25, GNU AVR ABI, AVR-GCC 7.3.0, `-Os -flto
-mcall-prologues -mrelax -fno-jump-tables -fno-exceptions -fno-rtti
-ffunction-sections -fdata-sections -std=gnu++11`, requested16 MHz /8 kHz.
Arithmetic needs the real `__AVR_ARCH__==25`, no `__AVR_HAVE_MUL__`, and the
separate explicit `LPX4_ENABLE_ASM=1`. C remains the default, including on
AVR25. The hardware player accepts only real `-mmcu=attiny88`.

## Exact software arithmetic

The [production math header](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4Math.h)
extends the project's [original standalone prototype](examples/lpx-avr25/README.md).
No manufacturer assembly listing was copied. Useful techniques:

- Unsigned carry-rotation multiplication plus independent signed corrections
  retains the entire 16x16 product, including both signed minima. Keep this
  full-product routine shared to limit Flash.
- LPC needs product bits 12..31. Shift a separate multiplier byte and capture
  outgoing product bits only in the last four rounds; never construct the
  discarded low 12 bits. Subtract the multiplicand in the final signed
  multiplier round. A zero or narrow history value takes an exact shorter path.
- Keep a Q4 accumulator and clear each product's low nibble before subtraction.
  This preserves **each original Q12 floor**; shifting the sum once is not a
  substitute for those floors. Ten full-range products and bounded excitation
  fit the signed 32-bit Q4 accumulator. Reverse traversal consumes history before
  shifting it, without another buffer.
- Byte-by-word excitation, exact gain 14 identity
  `floor((14*x+8)/16) = x + floor((4-x)/8)`, and common excitation values avoid
  full software products. PWM gain 130 uses an exact 24-bit shift/add identity,
  retaining rounding and clipping for the entire signed 16-bit domain.
- A ROM build can pin the **existing** header's flags, deemphasis and brightness.
  The parser explicitly rejects mismatches. Constant Q14 products discard
  unused bits and assemble only the additions required by the constant's bits.
  This changes neither compressed data nor decoded output. With no fixed-header
  defines, the portable dynamic library interface remains available.

`LPX4_ARCH=LPX4_ARCH_GENERIC` explicitly restores C arithmetic on a real AVR.
The real CPU and Flash-memory macros are never replaced. The SRAM512 profile
and its 96-byte dead-history workspace are reused; later fixed-ROM state
specialization is documented separately in the budget entry.

## Short interrupt with a bounded FIFO

The [player](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/player.cpp)
uses a 32-byte FIFO, 31 usable slots, prefill 24. Head/tail are atomic bytes;
final head+EOF publish together. Decode runs with interrupts enabled.
Timer0 CTC /8 /250 requests8 kHz; Timer1 fast8-bit PWM drives OC1A/PB1 at 62.5 kHz.

The separately enabled `LPX25_ENABLE_ASM_ISR=1` reserves r2/r3 across **all**
foreground compilation using `-ffixed-r2 -ffixed-r3`. r2 is scratch and r3
holds SREG. Only Z is pushed/popped; r1 stays untouched. FIFO alignment makes
`base | tail` valid without carry propagation. Foreground code stops the timer
after the final ISR drains the queue; no EOF check runs on every interrupt.
This assumes the standalone foreground drain loop and the measured interrupt
load. Arbitrary application ISRs or additional consumers need new admission.

The builder checks ELF function bodies for hardware MUL and forbidden uses of
the reserved registers, including linked runtime functions. It permits only
the standard ABI save/restore operations in GCC's prologue/epilogue helpers.
Do not link an unaudited library that keeps live values in r2/r3 during IRQs.
`LPX25_ENABLE_ASM_ISR=0` selects the equivalent C ISR independently of arithmetic.

Paired complete-player measurements: C ISR 63 cycles; selected ASM ISR 40 cycles
(2.5 us at 16 MHz), including hardware entry, vector jump and completed RETI.
Reserving only one register and saving r0 instead measured 44 cycles, +12 B
Flash and +1 B peak stack, so it was rejected. Reserving more registers is
not automatically faster: foreground spills matter. The C ISR remains a
valid alternative on the measured P4 stream. With the current size recipe,
its full image is6320 B and its decode mean1543.79 cycles; the selected ASM
ISR image is6284 B at1536.23 cycles. Register pressure and inlining must be
measured together; the old ISR-only screening is not a current size ranking.

## Admission and limits

Full simavr 1.6 execution uses an original bounded ATtiny88 model binding for
CPU memory, PortB, Timer0 and Timer1. Addresses/bits/vectors come from a
separate AVR object compiled with the retained official
[Microchip ATtiny_DFP 3.4.278](../../ATtiny88/Music/universal/vendor/README.md).
It does not substitute an ATmega device. Unused peripherals are not modeled.
The old music emulator lacks Timer0 Compare support and is not used for
playback admission; its AVR25 CPU supplies the separate arithmetic/ABI checks.

The adapter explicitly corrects two simavr 1.6 timing boundaries: hardware
IRQ entry was not charged by `avr_service_interrupts`, so four AVRe cycles
are added; RUNNING falls before RETI, so duration is finalized only after
that instruction retires. The selected handler is 36 cycles from the vector
through RETI, plus 4 cycles of hardware entry. Decode wall times include
the corrected entry cost. Timer callbacks and FIFO admission are rerun with
that clock advance; this is not only a correction to a printed ISR number.

The [source-bound receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/measurements.json)
records the complete matrix. Selected results, with active IRQs:

| Complete workload | Samples | Full Flash incl.audio | Mean decode wall cycles | Underruns |
| --- | ---: | ---: | ---: | ---: |
| P4 ROM, four reset chains | 76800 | 6284 B | 1536.23 | 0 |
| P6 real ROM prefix, eight chains | 76800 | 6418 B | 1509.66 | 0 |
| P6 + extras, changing spectra, lag145 | 51200 | 6254 B | 1803.85 | 0 |
| P6 + extras, clustered spectra, lag18 | 51200 | 6268 B | 1884.19 | 0 |

All PWM bytes equal a separately compiled portable C decoder, with ordinary
two-anchor LPC and unchanged source level. Output write intervals are
1991..2009 cycles, without accumulated rate drift. Static RAM is 435 B;
the observed worst stack is 67 B, leaving 9 B by the observer's SP convention.
The peak single decode call exceeds20k cycles; FIFO admission, rather than
average throughput alone, is essential. No further timer events occur after EOF.

The 16-slot control has 1 underrun; C arithmetic has 34177 underruns on its
declared control. They are rejected. The complete high-quality 19200-sample
ROM also passes timing, but its7354-byte image **exceeds 6656** and is not
admitted under the bootloader budget. The real P6 prefix preserves exactly
the first 9600 samples and fits the budget. This is bounded workload evidence,
not a guarantee for every valid stream or application load.

The arithmetic probe compares C / ASM / forced-generic on the same AVR25 CPU,
with active Timer1 interrupts, random/boundary products, signed extrema,
history shifts, rounding, clipping, r1, callee-save registers and stack balance.
Native regressions retain dynamic-header and SRAM512 behavior. Reproduction
commands are in the [player guide](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/README.md).

Physical hardware and the analog output have not been measured. The requested
16 MHz model does not extend the manufacturer's ordinary 12 MHz speed rating.

Primary references: [AVR200 / AN0936, revision 0936D](https://ww1.microchip.com/downloads/en/Appnotes/doc0936.pdf),
[ATtiny48/88 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf),
[simavr 1.6 timer API/implementation](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/avr_timer.c).

Timing-boundary references: [simavr 1.6 interrupt dispatch](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_interrupts.c), [RETI retirement](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_core.c).

## Share the decoder and select C or ASM multiplication

`Lpx4Math.h` now selects one private multiplication header:
`Lpx4MultiplyC.h` or `Lpx4MultiplyAvr.h`. Both expose the same exact signed
8x16, signed8 x unsigned16 and signed16 x signed16 functions. Parsing,
memory access, filters and the public decoder interface stay shared. The
ASM header selects hardware MUL for supported AVR5 and software products
for supported AVR25 from the real compiler ISA macros. There are two user
choices: portable C by default, or explicit `LPX4_ENABLE_ASM=1`. Forcing
`LPX4_ARCH_GENERIC` still selects C on AVR; unsupported targets also use C.

At the extraction commit4039d576 this was a source organization change with
no measured Flash, SRAM or speed gain. AVR-GCC7.3.0 rebuilt all18 Tiny88 matrix images byte-identically;
every timing/output/acceptance row also matches the previous matrix, including
the heavy P6 cases and rejection controls. All eight WebUI Nano HEX files
remain byte-identical and pass complete active-IRQ/WAV verification. Portable
C passes 5,768,584 independent cases per host configuration. Real AVR25
C/ASM/forced-generic each pass the same 17,958 arithmetic/ABI cases with
active interrupts; instruction counts are unchanged. Updated source hashes
in the matrix and WebUI catalog include both multiplication headers. The
following size changes are a separate measured improvement.

## Smaller exact AVR25 code without losing measured throughput

For constant0≤c<16384 and signed16 x, start a16-bit accumulator A=0 and repeat
`A=floor((A+bit[j]*uint16(x))/2)` for j=0..13. The addition uses its17th carry
bit during rotation. The result is exactly `floor(c*uint16(x)/16384)`;
subtract4*c if x<0 to obtain the signed floor. c=16384 is the identity.
This original project recurrence removes the old final two product steps,
low-byte collection, shifts and extra register pair. The existing portable
C expression stays explicitly selectable on AVR.

The fused synthesis macro also branches past the entire subtraction when
history is zero; it need not construct a zero product in three registers.
The local forward label is private to the MAC macro. Other history routes,
per-product rounding and the in-place history movement are unchanged.
Both kernels require supported AVR25, GNU AVR ABI and explicit ASM enable.
They preserve r1 and the ISR-reserved registers; SREG is declared clobbered.

The exact linked Tiny88 player was measured with AVR-GCC7.3.0, `-Os -flto
-mcall-prologues -mrelax`, FIFO32/prefill24 and the existing SRAM512 profile.
The selected ASM build adds `-fno-inline-small-functions`: on the tested P4
image it saves another98 B and reduces mean cycles and observed stack.
Other screened switches did not reduce size and were not adopted. This is
evidence for this compiler/workload, not a universal inlining rule.

All54 accepted2/3 kbit/s four-second streams pass exact independent PWM,
complete EOF/timer checks and zero underruns with IRQ active. Compared with
the baseline, full Flash decreases6–134 B and mean IRQ-active decode cost
decreases0.023–125.954 cycles/sample; no case gets slower. All27 sparse80
2 kbit/s images and12/27 ordinary-v5 3 kbit/s images fit6656 B. The remaining
15 require up to6718 B: timing passes under an explicit8192 B cap but the
bootloader-budget release gate rejects them. The original18-case matrix,
including dense P6 and rejection controls, passes again; its current values
are in the table above. No audio, sample count, source gain or codec parameter
changes were used to obtain these savings.

Arithmetic/ABI verification checks482,710 cases per C/ASM/forced-generic
backend, with active Timer1 IRQs and no lost interrupts. Seven fixed
coefficients cover every signed16 state; an independent integer recurrence
check covers1,032,211 state/coefficient cases. Anonymous before/after numbers
and code hashes are retained in
[the size admission](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/lowrate-size-measurements.json).
Private input bindings and generated media stay ignored. Reproduction and
physical/simulator limits remain as stated in the player guide.

## LPC full-width multiplication in pairs

The upper history byte can occupy the low product byte while the multiply
consumes it. On AVR25 without MUL, the 24-bit rotate supplies the next bit
in carry and replaces it with product bits. The last bit of the final pair
subtracts the multiplicand for the signed high byte. Keep the coefficient
sign correction and each individual Q12 floor. The explicitly selectable
C backend implements the same arithmetic. With AVR-GCC 7.3.0 and the AVR
GCC ABI at `-Os -flto`, the universal ATtiny88 image shrinks 6 bytes and
the heaviest workload saves 11.76 cycles per sample with IRQ. All 22
outputs match bit for bit and there are no underruns.
[Proof, test setup and rejected variants](../../Codecs/LPX/research/tiny-lpc-pairs-2026-11-13/README.md).
