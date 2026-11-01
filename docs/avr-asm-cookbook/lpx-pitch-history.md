# Exact bounded LPX pitch history

The [experimental patch](../../Codecs/LPX/research/v5-ram-reuse-2026-11-01/alternatives/pitch-history.patch)
supplies `LPX4_PITCH_HISTORY_SIZE` for 145..256 bytes in the v5-only decoder.
It is not installed in the production library: matched timing rejected it.
Reduced storage is not admitted as a speed-preserving target configuration:
145 fails the matched no-slowdown check below, and the other reduced lengths
have no speed admission.
The default remains 256, with its original byte-wrap arithmetic. Reduced sizes
require `LPX4_COMPACT_ONLY=1`; rejecting them in common-format builds is an
admitted-scope/compatibility guard. It does not assert that common-format lags
are larger. Define the same value in the library and every consumer because
the object layout changes.

```text
-DLPX4_ENABLE_SPEECH=1 -DLPX4_ENABLE_SPEECH_COMPACT=1
-DLPX4_COMPACT_ONLY=1 -DLPX4_PITCH_HISTORY_SIZE=145
```

V5 stores a seven-bit lag plus 18, so the maximum is **145 inclusive**.
For a history of size N, the read index is cursor-lag, adding N if negative.
The cursor wraps at N. At lag=N=145 the old value at the write cursor must be
read **before** storing the new code. Keep the predictor/store order intact in
both ordinary and exhausted-pulse paths. Initial history is zero-filled;
ordinary value copies and `begin` reset retain their existing semantics.

This is original project code using portable C++ arithmetic, with no new assembly
or hardware definitions. C remains available on AVR. The existing AVR5 backend
still requires explicit enable plus the compiler's supported architecture/MUL
defines. ATtiny88 targets AVR25 and has no hardware MUL; selecting the new RAM
option does not make that AVR5 assembly applicable.

## Measured size and correctness

ATtiny88, AVR-GCC 7.3.0, GNU ABI, compact-only C, LPC segments 2, tuning 0,
unroll 1, `-Os -flto -mcall-prologues -mrelax -fno-jump-tables`, function/data
sections and linker garbage collection. Register definitions come from the
installed AVR-GCC toolchain's Atmel `avr/iotn88.h` through `<avr/io.h>`.
The inherited short `vendor/include` search path did not exist; it did not
select the repository's newer Microchip ATtiny_DFP header. This provenance
correction does not change the measured images.
The core object falls **494 -> 383 bytes**, saving 111 bytes. Compact-only
already reserves three pulse slots; this is not an additional pulse-storage
saving. The polynomial arrays are still separate persistent workspace here.

Two 19,200-sample private streams, profiles 4/6, were linked into an unpaced
decode probe. Full Flash includes startup, tables, the actual stream, decoder
and observation loop; no audio bytes are subtracted. Five observation bytes
are included in static RAM. There is no queue, timer ISR or Micronucleus handoff
initialization in this probe.

| Profile | Full Flash, default 256 | Full Flash, 145 | Static RAM, 256 -> 145 |
| --- | ---: | ---: | ---: |
| 4 | 5364 B | 5368 B | 499 -> 388 B |
| 6 | 5856 B | 5860 B | 499 -> 388 B |

Default firmware binaries are byte-identical to the pre-option sources for
both linked probes. Native tests compare default/145/160/255/256 on 80 explicit
P4/P6 streams with lags 18/145, wrap boundaries, partial tails, copied/assigned
state and restart. Both private streams also have exact PCM16/PWM parity.
Compile-time checks reject 0/144/257 and common-format size 145. Reproduce the
synthetic checks with the [standalone research validator](../../Codecs/LPX/research/v5-ram-reuse-2026-11-01/reproduction/validate_pitch_history.py)
and `LPX4_HISTORY_SOURCE` pointing at the patched library directory; optional private stream
paths are supplied as a JSON list in `LPX4_PITCH_HISTORY_FIXTURES`.

## Timing limit of this ATtiny88 C probe

The existing transpiled AVR CPU executed each actual instruction at the explicit
16 MHz board clock. Its ATtiny88 IJMP/ICALL/RET cycle and stack behavior was
checked separately. The older reference CPU lacks IJMP and was not used to
claim completed timing. No host-wall-clock speed comparison is made.

| Profile | Total cycles, all 19,200 samples | Average cycles/sample | Worst inter-output gap |
| --- | ---: | ---: | ---: |
| 4 | 123469507 | 6430.7035 | 44973 cycles |
| 6 | 118072229 | 6149.5953 | 45403 cycles |

Both complete PWM outputs equal the native decoder. The earlier direct 145-slot
prototype and the final opt-in firmware binaries are identical, so their timing
is identical; an ATtiny88 256-to-145 decode-speed delta is **not measured**. The 256-byte
history probe leaves only 13 bytes before any stack and cannot serve as a safe
running ATtiny88 baseline.

The observed stack high-water mark is 55 bytes over each complete unpaced run,
including startup, with minimum SP 0x2c8 and a conservative 68-byte gap above
the 388-byte static allocation. This excludes ISR stack and buffering; it is
not a worst-case or interrupt-active stack admission.

An 8 kHz stream at 16 MHz allows only 2000 cycles/sample. These unpaced averages
already exceed it by more than three times. Therefore this RAM reduction alone
does **not** admit ATtiny88 LPX playback at 8 kHz. No timer/IRQ playback image,
underrun success, physical-board support or reduced-sample-rate profile is
claimed. Keep the original 8000 Hz stream semantics. More RAM reuse must be
evaluated separately for exactness and matched target timing.

## Matched AVR5 speed check: rejected for slowdown

Eight complete ATmega328P images compare the same two streams at 256/145 slots,
with portable C and explicitly enabled AVR5 assembly. Use the same GCC/options,
segments 2, unroll 1 and tuning 0, with queue 512/prefill 384, normal active
Timer1 ISR and zero additional synthetic IRQ load. The current `profile.cpp`,
`sim_profile.c` and streaming `profile_durations.h` provide all 19,200 decode
intervals in every image. Duration includes ISR and instrumentation overhead;
these are matched target CPU cycles, not host execution times.

| Profile/backend | Mean cycles/sample, 256 -> 145 | Maximum 160-call sum, 256 -> 145 | Underruns, 256 -> 145 |
| --- | ---: | ---: | ---: |
| 4 / C | 3316.5361 -> 3351.9470 | 588546 -> 594503 | 13837 -> 14175 |
| 6 / C | 3154.3432 -> 3188.8460 | 560852 -> 566570 | 12323 -> 12644 |
| 4 / ASM | 851.5808 -> 863.7254 | 155382 -> 156296 | 0 -> 0 |
| 6 / ASM | 789.1494 -> 801.5800 | 142067 -> 143942 | 0 -> 0 |

All eight complete PWM outputs match native output. Static RAM falls
1039 -> 928 bytes, while full Flash grows 2 bytes in C and 26 bytes in ASM.
Every mean and maximum 160-call sum worsens: approximately 1.07..1.09% mean
slowdown in C and 1.43..1.58% in ASM. Therefore 145 is retained only as an
explicit experimental RAM tradeoff; it fails the requested no-speed-regression
condition. These AVR5 results are not ATtiny88 assembly or playback admission.

The [full RAM-reuse report](../../Codecs/LPX/research/v5-ram-reuse-2026-11-01/README.md)
also records rejected sequential, union and dead-ring workspace alternatives.

One observer initialization failed before CPU execution because LTO/GC removed
host-only hardware-address metadata. That image/log is retained privately.
The corrected fixed eight-image run retains the profiling ABI using the
existing `benchmark_speech_flash.external_symbols` policy and linker `-u` flags;
no completed simulation was repeated. Media, binaries and their fingerprints
remain in ignored local receipts.
