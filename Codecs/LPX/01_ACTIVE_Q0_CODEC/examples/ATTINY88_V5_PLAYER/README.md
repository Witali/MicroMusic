# ATtiny88 / 16 MHz LPX v5 player

The public Tiny88 firmware uses the existing **AVR25 ASM arithmetic and short
ASM ISR** to play the measured P4/P6 and explicitly enabled sparse80 speech
streams at 8 kHz without hardware multiplication. The SRAM512 workspace
profile is reused. FIFO32 remains the
default: 31 usable slots, prefill 24. `--queue 24` selects 23 usable slots and
prefill 18, saving eight static bytes; 16/24/32 are explicit build choices.
Speex is excluded from the Tiny88 profile.

The hard full-image limit is **8192 bytes**, including compressed audio,
initialized data, startup, decoder and ISR. Larger limits and images are
rejected. The builder also proves that the embedded audio array exactly
matches the input. Treat an image around or above **6 KiB** as a USB bootloader
fit warning: the standard MH-ET LIVE region is actually **6012 bytes**. An
image above 6012 bytes requires an ISP programmer. To enforce USB fit during
building or verification, pass `--flash-limit 6012`. The former 6656-byte
default was a historical budget. Nothing is flashed automatically.

Repeated playback with active interrupts must reproduce every portable C PWM
sample, drain the queue and stop Timer0 without underruns. The FIFO covers
individual frame conversions exceeding 20k cycles; a mean near 1500 cycles is
not a worst-case bound. Additional application RAM or IRQ work requires a new
complete timing/stack check.

OC1A/PB1 supplies62.5 kHz fast PWM. Timer0 CompareA requests a new sample every
2000 CPU cycles. The foreground drains and stops after the last sample;
Timer1 keeps the final duty. This is a standalone one-shot/reset-chain driver,
not an Arduino sketch sharing timers or interrupt vectors with a framework.

## Current complete-player results

The selected public recipe is FIFO24 with multiplication unroll2. All nine
complete phrase/profile combinations pass one-shot playback: **141,708 PWM
samples**, byte-exact against both the independent C reference and the
existing public WAV, with active interrupts and zero underruns. No phrase,
sample count, stored stream bytes or source gain is changed.

| Complete release image measurement | Result |
| --- | ---: |
| Flash, including the original audio | 5418..7132 bytes |
| Program Flash after subtracting the verified single audio array | 4947..5233 bytes |
| Static SRAM, including FIFO | 422 bytes |
| Largest observed stack | 66 bytes |
| Smallest observed stack margin | 23 bytes |
| PWM write intervals at requested 16 MHz | 1991..2009 cycles |
| Images fitting standard 6012-byte USB region | 6 of 9 |

The other three images fit physical Flash and require ISP loading. The full
19,200-sample P4 example fits exactly 6012 bytes. The stack margin uses the
observer's conservative SP convention and is bounded evidence for these
images. The separate paired memory runs decode every combination twice.
[Current local catalog](../../../../../web-player/firmware-lpx-attiny88.json)
retains per-image values; [anonymous budget measurements](budget-measurements.json)
bind the before/after sources and the full timing/control scope.

Matched before/after runs with the same complete phrases and repeat count save
**202..272 program bytes**. The largest increase in mean IRQ-active decode
cost stays below **0.510%**; every output sample stays exact and all nine runs have zero
underruns. The smaller FIFO and loop arithmetic are a measured memory/Flash
tradeoff with enough timing headroom for these workloads.

## Build and independently verify

Requirements: Python3 standard library, AVR-GCC 7.3.0/AVR-LibC, host g++,
simavr 1.6 development headers/library and libelf. Existing Linux tools can
be used from Windows with `--wsl Ubuntu`. From the repository root:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/verify_attiny88_player.py \
  web-player/audio/lpx-bread/compact.lpx build/tiny88-player
```

Add `--queue 24` for the measured smaller-RAM variant, and
`--enable-sparse80` for v8/mode15 streams. Use `--repeat 2` to check a complete
phrase twice without trimming or repacking its source bytes.

The selected public recipe combines `--queue 24 --mul16-unroll 2`.
The general builder/verifier retain FIFO32 and unroll16 defaults. Factors
1/2/4/8/16 are explicitly selectable; 16 fully unrolls the software product,
while smaller factors group the same exact rounds in a loop. The SRAM512
fixed-P4 build also keeps only the 33 reachable cosine half-grid words for
segments 1/2, saving 64 table bytes without changing rounding or coefficients.
P6, unpinned headers and four-segment builds retain their prior table/helper.

The verifier explicitly enables arithmetic ASM and the selected ISR. It builds
the full AVR image and a separate native **dynamic-header C reference**, runs
the actual linked ELF with both hardware timers active, and compares every
PWM byte. `verification.json` must contain `accepted:true`. It also requires
exact sample/timer counts, no underruns, empty final queue, timer stop, bounded
output intervals, positive observed stack margin and the complete Flash cap.
No firmware counters or test media arrays are inserted for timing measurement;
zero-byte ELF symbols delimit the production decode region.

For build-only use:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/build_attiny88_player.py \
  web-player/audio/lpx-bread/compact.lpx build/tiny88-build --enable-asm --asm-isr
```

Build-only outputs remain marked `timing_verified:false`. Without explicit
ASM flags, C is selected. `--c` and `--c-isr` on the verifier independently
select C arithmetic and C ISR. The measured C arithmetic does not meet8 kHz.
The C ISR is an admitted alternative for the measured P4 example.

ROM builds pin the existing stream's format flags and two fixed filter
constants; mismatches are rejected. No codec parameters, compressed bytes or
quality are changed. In the SRAM512 profile those three fixed values no longer
occupy private object storage: decoder state is **398 -> 393 bytes**. Generic
library builds with unpinned headers retain the 398-byte SRAM512 state, dynamic
parameters and other architectures' portable interface. Use identical profile
and fixed-header defines in every translation unit because the layout changes.

The FIFO32 ASM IRQ costs 40 cycles; FIFO24 costs 44 cycles, including four-cycle
hardware entry and completed RETI. The four-cycle cost is **0.2% of the CPU**
at 8000 interrupts/s and 16 MHz. The simavr 1.6 adapter explicitly accounts for
both boundaries before admitting playback.

The short ISR reserves r2/r3 with whole-program `-ffixed-r2 -ffixed-r3`.
The builder audits **linked ELF function bodies**, including library code,
for uses outside the ISR and standard ABI save/restore helpers. Handwritten
arithmetic and ISR selection are separate, and real device/memory macros are
preserved. The official ATtiny_DFP 3.4.278 header is reused in place; a separate
header-derived object configures the observer, never the production ELF.

## Reproduce the complete matrix

Run these in Linux/WSL from the repository root:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_matrix.py build/tiny88-matrix
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_matrix.py build/tiny88-matrix24 --queue 24
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_matrix.py build/tiny88-matrix24-loop2 --queue 24 --mul16-unroll 2
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py build/tiny88-math
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/build_avr25_math.py build/tiny88-math-loop2 --mul16-unroll 2
```

Then run the project's existing Node executable from the same checkout:

```sh
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/tiny88-math
node Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr25_math.mjs build/tiny88-math-loop2 --exhaustive-fixed
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_fixed_header.py
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_sram512_profile.py
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_math_backend.py
```

The matrix covers real P4, an exact whole-packet real P6 prefix, P6 extra
innovations with changing/clustered spectra and lag 18/145, long reset chains,
ten partial/complete tails, C ISR, C arithmetic rejection, FIFO16 rejection,
and explicit Flash-cap rejection. The full P6 image is also checked against
the 8192-byte physical cap; the old 7354-byte measurement exceeded the former
6656-byte gate and the standard 6012-byte USB region. Generated audio, logs,
ELF/HEX and reference PWM stay in ignored
`build/`. [Anonymous measurements](measurements.json) retain numerical results
and source hashes without audio or private input fingerprints.

The final FIFO24/unroll2 matrix has **18 cases: 16 admitted and two intended
timing rejections**, with the explicit smaller-Flash-cap rejection exercised
separately. Five arithmetic factors each pass 26,262 cases on C, ASM and
forced-generic backends: **393,930 backend-case runs**, including ABI and live
interrupt checks. Exact P4-table tests cover 1808 nodes, 48 scenarios and 120
complete PCM/PWM comparisons. The C arithmetic remains an independently
selectable fallback; the selected release target uses ASM.

To regenerate the verified Tiny88 catalog and retain its assets in the local
web player, run:

```sh
python3 tools/build-tiny88-speech-catalog.py --retain --queue 24 --mul16-unroll 2
```

Add `--wsl Ubuntu` on Windows. This builds and verifies whole phrases, then
copies the local HEX/catalog assets; it performs no upload or flashing.

## Historical 2/3 kbit/s speech and size measurements

The measurements in this section predate the later fixed-state/FIFO and
arithmetic-loop changes. Their original source-bound receipts remain intact;
their 6656-byte release gate is historical. Current loading decisions use the
8192-byte physical cap and the 6012-byte standard USB application region.

`--enable-sparse80` explicitly enables v8/mode15 for 2 kbit/s speech; ordinary
v5/P4 carries the accepted 3 kbit/s selections. Both use the same decoder,
FIFO, ISR and selectable C fallback. New source streams are not repacked or
trimmed by the firmware builder.

The final 54 four-second selections were rebuilt and replayed on Tiny88:
1,728,000 exact PWM samples, active interrupts, zero underruns. All 27
2 kbit/s images fit the 6.5 KiB limit (5.826–6.227 KiB); 12 of 27 3 kbit/s
images fit. The other 15 pass timing under the explicit 8 KiB experiment cap
but occupy up to6.561 KiB and are not admitted with the bootloader reserve.
At that stage the default builder rejected images exceeding6.5 KiB.

The bounded size changes save6–134 bytes with no increased mean decode cost
on any of these54 streams. Exact 14-step fixed-Q14 attenuation discards unused
product bits; zero history skips a whole MAC subtraction. The measured ASM
recipe also uses `-fno-inline-small-functions`; the C recipe is unchanged.
All18 older matrix configurations retain their intended acceptance/rejection.
The P4 ROM changes6418→6284 bytes and1574.49→1536.23 mean IRQ-active cycles;
its observed stack changes67→60 bytes. The real P6 prefix saves36 bytes and
30.39 cycles/sample. [Anonymous before/after measurements](lowrate-size-measurements.json)
pin the54 workloads and the exact source contexts.

With private inputs available, reproduce the paired corpus replay using
`tests/verify_attiny88_lowrate.py MANIFEST build/tiny88-lowrate --jobs 2`;
add `--wsl Ubuntu` on Windows. Only its anonymous `summary.json` is suitable
for retention; media, bindings and other outputs remain in ignored `build/`.
For complete fixed-Q14 arithmetic/ABI coverage, add `--exhaustive-fixed` to
`verify_avr25_math.mjs`: 482,710 cases per C/ASM/forced-generic backend with
active interrupts, including all signed16 states for seven coefficients.

The original bounded simavr model binding covers CPU memory, PortB and the two
timers used by this image. It is not a full ATtiny88 board model. Physical-board
and analog behavior are unmeasured;16 MHz is the requested clock, above the
ordinary device speed rating. The [cookbook](../../../../../docs/avr-asm-cookbook/lpx-avr25.md)
records techniques, correctness constraints, measured limits and references.
