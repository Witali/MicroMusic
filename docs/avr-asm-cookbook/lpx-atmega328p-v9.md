# The same universal LPX v9 core on AVR5

Measured in native simavr 1.6 on ATmega328P at 16 MHz, with 8 kHz output,
FIFO32/prefill24, the SRAM512 decoder layout, two LPC segments, and runtime
stream parameters. The core is the same one used by the frozen Tiny88 v9
admission, at source baseline `a648f430`; the receipt checks relevant source
hashes instead of requiring that Git HEAD remain unchanged.

This is a private adaptation of the Tiny-style one-shot player, using a normal
compiler-generated C ISR. It is not a measurement of the production Nano
firmware or a physical board. Production player/core files are unchanged.

| Public input | AVR5 decoder CPU | Complete IRQ | Total cycles/sample | Tiny88 total | AVR5 program | Tiny88 program |
|---|---:|---:|---:|---:|---:|---:|
| Chego, sparse80 / about 2 kbit/s | 701.490 | 64 | 765.490 | 1547.308 | 5095 B | 5605 B |
| Chego, P4 | 723.136 | 64 | 787.136 | 1605.610 | 5094 B | 5604 B |
| Chego, P6 | 727.017 | 64 | 791.017 | 1598.128 | 5094 B | 5604 B |
| Changing sparse80, lag18, maximum pre-emphasis | 773.196 | 64 | 837.196 | 1770.964 | 5095 B | 5605 B |

Program means the complete application image minus its verified embedded audio
array, including the player, vector table and ISR. Full AVR5 images are
5392/5616/5870/5456 B respectively. Static RAM is 433 B; maximum observed stack
is 71 B, leaving 1543 B on the Mega's physical 2048 B SRAM. The decoder still
uses the same SRAM512 layout as Tiny88. The Tiny88 ISR costs 38 cycles and its
stack is 67 B, so this is a whole-target comparison with different safe ISR
implementations.

In binary units, the Chego2k program is **4.976 KiB** (5095 B), its audio is
**0.290 KiB** (297 B), and the complete image is **5.266 KiB** (5392 B).
The matched Tiny88 program is 5.474 KiB (5605 B), or 5.764 KiB including audio.

At 16 MHz, Chego2k needs 47.843 microseconds/sample for the measured decoder
plus complete ISR, or 38.27% of the 125-microsecond sample period. The heavy
control needs 52.325 microseconds, or 41.86%. These figures exclude foreground
queue management and idle time. Per-call frame work can exceed one sample
period; the FIFO smooths it. All four full playbacks reproduce the independent
explicit C and frozen PWM oracle exactly, with zero underruns and positive
stack margins.

## Preserve ABI state when using MUL

Applicable target: classic AVR5 / ATmega328P, hardware `MUL`, GNU AVR ABI,
AVR-GCC 7.3.0, avr-libc 2.0.0. The arithmetic backend is explicitly enabled
with `LPX4_ENABLE_ASM=1`; real compiler architecture/MUL macros select AVR5.
The portable C fallback remains explicitly selectable on the same target.
Memory access is selected independently by the real AVR compiler macros.

Do not copy the Tiny88 ISR's reserved r2/r3 scheme onto this target. The AVR5
`lpx4Mul16` inline assembly explicitly clobbers r2, which `-ffixed-r2` does not
prevent. Use the ordinary C ISR here: it saves/restores r0, SREG and r1, clears
r1 for its C body, and restores the interrupted value. An IRQ can arrive after
`MUL` but before the foreground clears r1. The external observer saw nonzero r1
at IRQ entry 88/85/156/167 times in the four ASM playbacks and checked r0/r1
restoration after every complete RETI. It does not assume r1 is zero at entry.

The private port uses `-mmcu=atmega328p` and includes `<avr/io.h>` normally.
It captures the actual compiler-selected Microchip `avr/iom328p.h`, retaining
its full copyright/license in the generated copy and pinning its hash in the
receipt. Timer0 uses `TCCR0A.WGM01` and `TCCR0B.CS01`; its compare-A vector is
14. Timer1 OC1A remains PB1. Register addresses and bits are compiled into an
unlinked observer metadata object from the header, never duplicated by hand.
The observer uses simavr's native Mega CPU/peripherals, with the established
simavr1.6 four-cycle hardware-entry adapter and complete RETI accounting.

Header provenance: compiler-selected avr-libc 2.0.0,
[avr-libc project](https://avrdudes.github.io/avr-libc/). Its actual header
contains Microchip's 2020 BSD-style notice; no vendor implementation is adapted
or published by this experiment. Original project observer/port transformations
are retained below. Linked simavr is GPL-3.0-or-later; its implementation is not
copied into the repository.

## C control and reproduction

The Chego2k C control is smaller (4815 B program, 5112 B full image), but fails
the real-time gate: 2277.106 active decoder CPU + 64 complete IRQ = 2341.106
cycles/sample, with 1997 underruns. All 9831 genuinely dequeued samples still
match C/frozen PWM exactly. The observer selects genuine samples by nonempty
queue count at IRQ entry, including genuine byte128; it never filters silence
by sample value. This is a throughput rejection, not an arithmetic failure.
No other C formats were admitted or measured in this retained run.

Both controls use the same `-finline-small-functions`, with
`-Os -flto -mcall-prologues -mrelax -fno-jump-tables -fno-exceptions -fno-rtti`,
function/data sections, `LPX4_FUNCTION_TUNING=0`, and the same player geometry.
The complete sanitized option lists and explicit backend macro checks are in
the [source-bound receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/atmega328p-v9-measurements.json).
The result compares the selectable whole arithmetic implementations under this
recipe; it does not attribute every saved cycle solely to a single instruction.

From a clean checkout with AVR-GCC, g++, simavr1.6 development files, libelf and
Python standard library, use a fresh ignored output directory:

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_atmega328p_v9.py build/mega328-v9 --wsl Ubuntu
python -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_atmega328p_v9.py
```

Omit `--wsl Ubuntu` on Linux. The verifier builds private source copies, obtains
the real device header, regenerates all four public fixtures, checks frozen
input/PWM hashes, runs four ASM cases and one explicitly selected matched-flags
C control, and leaves complete ELF/listings/timing/PWM evidence under `build/`.
It fails if relevant core sources differ from the Tiny comparison. A C timing
rejection is preserved in the report; ASM playback must pass the strict full
gate. The small unit tests check receipt/source binding, fixture reconstruction,
private port source binding, real backend flags and the recorded outcomes.
