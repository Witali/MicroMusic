# Optional low-rate profiles

Work proceeds in separate implementation/admission stages. Target remains
ATmega328P, 16 MHz, 2 KB SRAM; explicit AVR ASM is the playback target.
Portable C fallback selection and the existing compact Q7/16-tap QMF remain.
Original Xiph 1.2.1 files, mode tables and BSD provenance stay unchanged.

## Stage 1: NB5.95 / WB7.75

`SPEEX_ENABLE_NB2=1` adds submode 2: 119 meaningful bits / 15 bytes, 160
samples at 8 kHz. Combined with HB1 it uses 155 bits / 20 bytes, 320 samples
at 16 kHz. Padding is ignored; length/mode/HB checks precede state updates.
Feature defaults to zero. `--low-rates 1` selects it in the AVR builders.
Feature bits select NB2=1, NB8=2, NB1=4; availability is described per stage.

LBR LSP/LPC and IIR are shared. Ten-sample pitch/innovation primitives are
reused with `exc_10_16_table` (160 B), and the 32 no-subframe-correction
energies are generated from upstream constants. NB3 and NB2 share one
short-pitch controller with the codebook selected outside its sample loop.
HB1 reuses the existing excitation buffer and fold kernel, not a new frame.
The no-correction maximum scale is 115088100, within the existing 121000000
primitive domain; the same pitch gain codebook keeps existing signed24 bounds.

Initial screening: three retained RU/EN clips, 40 frames each. NB matches
untouched Xiph PCM; WB matches the independent established compact-profile
oracle, including first-frame reset replay. The continuous WB player checks
the same 120 frames with timers/IRQ, exact s16/PWM and zero underruns.
These are initial tests, not the final full-corpus admission.

AVR GCC 7.3.0, existing mixed Os/O2/O3, LTO/mcall-prologues/mrelax;
avr8js 0.21.1. NB-only mailbox is 11546 B Flash / 1094 B static SRAM;
WB mailbox 18350 / 1275 B, or +948 / +1342 B Flash versus the minimum
NB8/WB9.8 images. The smaller packet mailbox accounts for the SRAM difference;
no new core synthesis buffer is allocated. WB screen mean 245158.833 cycles,
maximum 251095; these exclude output/interrupts. IRQ player leaves 423 B SRAM,
minimum queue 29 with no added foreground load. No board timing is claimed.

## Next stages

Add NB3.95/WB5.75 forced-pitch reconstruction, then NB2.15/WB3.95 noise and
vocoder processing, preserving the original random sequence and state across
rate changes. Follow with full corpus, padding/error/reset/mixed-mode checks,
default-image identity, C export, Flash delivery and active-IRQ admission.
Do not infer reduced CPU cost merely from reduced bitrate.

## Stage 2: NB3.95 / WB5.75

`SPEEX_ENABLE_NB8=1` adds 79-bit / 10-byte NB and 115-bit / 15-byte WB
packets. `--low-rates 3` enables both new pairs. The original forced pitch
builds prediction before adding innovation; feeding completed output back
would change PCM. For lags 17..144, at most two rounded predictor ancestors
are needed within a 40-sample subframe. Recover those from completed history
and pass small ranges through the existing three-tap kernel with outer gains
zero. A 24-byte stack edge replaces an additional 80-byte frame buffer.
The common HB1 controller selects the 20-sample/32-vector Flash codebook and
feeds the same ten-sample and folding primitives. LSP/LPC/IIR/QMF stay shared.

The same three-clip initial screen passes 120 NB and 120 WB exact/reset frames.
The WB player passes 120 continuous frames with timers/IRQ, exact PCM/PWM,
zero underruns, queue minimum 13 and 397 B free SRAM at zero extra load.
Both pairs together use 13044 B NB / 20024 B WB bare Flash. The original
minimum WB image remains byte-identical with lower rates disabled.
Full-corpus timing and mixed-mode admission remain the final stage.

## Stage 3: NB2.15 / WB3.95 (approximately 4 kbit/s WB)

`SPEEX_ENABLE_NB1=1` adds 43-bit / 6-byte NB and 79-bit / 10-byte WB packets.
`--low-rates 7` enables all three new pairs; the NB4 feature is independent.
There is no invented 4.000-kbit/s format: WB3.95 is the standard HB1 combination.
DTX/PLC, enhancer and highpass remain outside the restricted profile.

The original 32-bit LCG sequence starts at 1000 and advances 160 times per
NB1 frame. HB1 regenerates it from a four-byte frame-start seed snapshot.
Its five possible symbols are scaled once, with pulse/noise weights hoisted
out of the sample loop. The existing 80-byte output area holds 40 byte indices
in its upper half and is expanded forward safely. Vocoder phase fits uint8;
only exact rounded/weighted signed16 state is retained. The feedback mean
keeps its required int32 accumulator and original rounding. No PCM precision
change or new full-frame buffer is involved.

The initial literal version passes 640 exact/reset WB frames but averages
415676.1 cycles (maximum 419657), exceeding the frame budget. Exact finite-
domain/word optimizations reduce the same 16x40-frame screen to 266736.491
cycles (maximum 270622). These timings exclude ISR/output. All PCM is still
exact to the established compact-profile oracle. All three new pairs together
use 22022 B WB bare Flash, 1288 B static SRAM at a 10-byte mailbox width.
The initial three-clip/120-frame WB IRQ screen passes with exact s16/PWM,
zero underruns, min queue 18 and 395 B free SRAM, at zero extra load.
NB2.15 independently passes 120 original-Xiph exact/reset frames.

`tests/prove_low_noise.py` checks every signed16 high word against the
original noise equation, all 32 legal scales, state/phase bounds and both
byte orders for alias expansion. The literal slow comparison patch is retained
under the cookbook examples; it is not an admitted playback backend.
See [the reusable technique](../../../docs/avr-asm-cookbook/speex-five-symbol-noise.md).
Final full-recording, mixed-mode, bad-packet and production delivery checks
are still required before concluding the admission stage.
