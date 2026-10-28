# AVR program-Flash size profiles

These are explicit build recipes for ATmega328P/AVR5,16MHz,8kHz PWM,
AVR-GCC7.3.0. Encoded audio is unchanged. No new assembly or hardware
definitions are added. Keep all defines consistent across the core and its
consumers because format flags affect class layout.

## Primary speech development target

Current speech work targets `LPX4_COMPACT_ONLY=1` with the measured small-code
recipe below. Encoder refinement uses the existing v5 format; see
[SPEECH_COMPACT.md](SPEECH_COMPACT.md#further-v5-only-encoding). The general
library defaults remain available for consumers of earlier formats.

## Retained default and compact-only profile

`LPX4_COMPACT_ONLY=0` is the default. It preserves all formats enabled by
the existing speech/v3 feature flags. No global compiler defaults or old
audio streams are silently changed.

`LPX4_COMPACT_ONLY=1` requires both `LPX4_ENABLE_SPEECH=1` and
`LPX4_ENABLE_SPEECH_COMPACT=1`. This explicit profile accepts only v5
profiles4/6, rejecting versions2/3/4. It removes their parsers and unused
state, fixes excitation mode/limit to v5 constants, and reduces sparse
storage from ten entries to three. The optional extra-pulse collision and
insertion rules, spectral synthesis, restart and tail validation are shared.
Use pure `speech_compact.py` repacking when converting a v4 speech asset;
legacy LPX8/12/16 assets need the common build.

The portable C fallback remains available, including on AVR. The size profile
does not enable assembly: `LPX4_ENABLE_ASM=1` is still a separate opt-in and
requires a real supported target. Flash access follows platform macros,
independently of arithmetic selection.

## Measured small-code recipe

The selected recipe uses these compile/link options in addition to normal
include paths, source files and target options:

```
-mmcu=atmega328p -DF_CPU=16000000UL -Os -std=gnu++11
-fno-exceptions -fno-rtti -flto -mcall-prologues -mrelax
-DLPX4_AVR_DOT_UNROLL=1 -DLPX4_FUNCTION_TUNING=0
-DLPX4_ENABLE_ASM=1 -DLPX4_V3_FEATURES=24
-DLPX4_ENABLE_SPEECH=1 -DLPX4_ENABLE_SPEECH_COMPACT=1
```

Add `-DLPX4_COMPACT_ONLY=1` for the speech-only build. Apply LTO/prologue/
relax options at both compilation and linking. This is a measured AVR recipe,
not a recommendation to pass AVR options to other architectures.

Default unroll9/local-O2=7 remains unchanged in the library. Smaller unroll
and global Os, combined with LTO/shared prologues/link relaxation, produced
the smallest measured program in the bounded24-candidate screen. Adding
function/data sections and linker GC was slightly larger for the winner;
do not assume that more size-related flags always reduce size.

Reproduce the build and full saved-PWM checks through:

```
python tools/benchmark_speech_flash.py verify --source . --output BUILD_DIR \
  --avr-bin AVR_BIN --runner SIM_RUNNER --lib SIM_LIB --wsl Ubuntu \
  --candidate unroll1-tune0-lto-call-relax --compact-only
```

Omit `--compact-only` for the common build. `screen` compiles the bounded
candidate set; it is a size screen, not real-time admission. The harness
retains every externally observed `profile_*` symbol even with LTO/GC and
verifies hardware-address metadata and the exact embedded audio array.
No size win is claimed from stripping the measurement framework.

Program Flash means `.text + .data - exact embedded stream bytes`, including
startup, playback/profiling code, codec tables and runtime helpers. It is
neither raw ELF file size nor an isolated decoder-library footprint. LTO,
relaxation and the known ROM array size can affect emitted code; measured
sizes are reported over the actual tested images.

All eight fixed enhanced streams, long active-IRQ controls, legacy common
streams, C fallback and integer math are checked separately. The optimized
C fallback remains numerically correct but misses the8kHz deadline on the
measured AVR setup. See the Flash research report for exact sizes, stack,
timing, flags, hashes and supported-workload limits.

[Measured Flash results and retained verification](../../research/speech-flash-2026-10-26/README.md).

## Reusing the builder for legacy profiles

The Python API `environment(source, avr_bin, legacy_only=True)` explicitly
disables the v4/v5 speech parsers while retaining the existing v2/v3 feature
mask24. It cannot be combined with compact_only. The default environment
and all previous common/v5-only compiler commands are unchanged.

`validate_profile_smallcode.py` reuses the same compile_image/simulate,
symbol retention, exact audio exclusion and saved-PWM checks for the
completed8/12/16 study. It does not reinterpret a v5-only build as legacy
compatible. Its current-source admission and continuous controls are
separate from the earlier speech measurements.


## Complete-recording firmware cost

```text
python tools/measure_speech_firmware.py BUILD/firmware SEGMENT0.l4hy SEGMENT1.l4hy --avr-bin AVR_BIN
```

This separate collector links a real v5-only ELF for the complete recording,
including every reset segment, Flash pointer/length tables, startup, runtime,
codec tables and the retained playback/profiling harness. Shared code is counted
once. Full Flash is `.text + .data`; `program_flash_bytes` additionally subtracts
only the exact, distinct embedded stream arrays proved against ELF symbols and
the loaded binary. Duplicate segment content must still occupy distinct ranges
before its cost can be subtracted twice. Alignment and linker relaxation can
change non-stream cost by a byte, so do not replace measurement with a constant.

The derived harness resets the decoder between segments while output IRQs and
the queue continue. Reset time is inside the measured producer interval. It
uses the same manufacturer/AVR-LibC register definitions and externally retained
profiling metadata as `profile.cpp`. This multi-segment harness has a different
footprint from the old one-array study; compare candidate images built with the
same collector, reset geometry and flags. It is a diagnostic firmware, not the
planned minimal production player.

`cost.json` records `lpx-v5-firmware-cost-v1`: ordered stream hashes, total stream
bytes, full/program Flash, source/build/image fingerprints and explicit exact
embedding/complete-image evidence. The build fingerprint includes toolchain,
headers, flags, source inventory, derived harness and segment sample counts;
stream content is bound separately. Source or binary changes invalidate the
cache. These local fingerprints detect stale data, not maliciously fabricated
third-party evidence.

All generated files must stay under this checkout's ignored `build/`. APIs
`measure(streams, output, avr_bin)` and `simulate(...)` accept complete bytes-like
v5 segments; the CLI also protects source stream paths. At most 255 segments
are supported. Link failure or unknown cost never means zero Flash. The
selector separately enforces the hard target capacity, such as 32768 bytes for
the tested ATmega328P; no bootloader reservation is assumed.

Add `--runner SIM_RUNNER --lib SIM_LIB --wsl Ubuntu` for complete-chain active-IRQ
simulation and independent-model PWM verification. `--irq 100` adds 100 deliberate
cycles per audio tick. Timing and physical-board status are separate from size
evidence: a linked image is not real-time admission, and simulator success does
not establish board/analog-output behavior. The arithmetic C fallback can be
measured through `measure(..., assembly=False)`; no new assembly is introduced.


The current `sim_profile.c` records every decode duration. Host-only
`profile_durations.h` retains a 160-duration ring, 64-bit totals/maxima and exact
40/80/160-window maxima. Reports identify `decode_statistics=streaming-v2`;
`decode_timing_samples` must equal the complete produced/played count. Updating
this host runner changes **zero AVR Flash bytes**. The existing 125 simulated
second hard stop remains; a timed-out/incomplete run never gains admission.

Historical capped reports require explicit `historical=True` in
`validate_timing`/`simulate`, or `--historical-runner` on the profiling CLIs.
They remain labeled historical and may cover only the first64000 durations.
Never compare those totals with a new complete-chain average. Complete PWM,
output ticks, produced/played counts, errors, underruns and stack checks remain
mandatory in either mode. C fallback diagnostic runs can still report underruns;
they are not declared real-time merely because their output values are exact.

## Separate build and validation provenance

`environment()` and `build_provenance()` describe AVR inputs: compiler/linker,
AVR/GCC header trees and libraries, the linked core's local include closure,
harness/flags and retained ABI. The complete source inventory remains available
for decoder/model correspondence; uncompiled oracle tables do not force a relink.
The complete generated voice header and ordered streams bind each image cache.
Host-only Python/runner/model changes no longer enter its compilation key.

Artifact inspection has a separate fingerprint: changing its tools or host code
requires fresh section/embedding proof against the same ELF. Timing validation
binds the runner binary, its resolved loader libraries, host code/model tables,
Python/package versions, expected complete PWM and exact image/cost. Changing
those inputs forces fresh validation while reusing the identical AVR ELF.
Corrupt image, metadata, timing or PWM records are rejected; no fingerprint is a
substitute for independently matching source streams and complete output.

Alternate production builders may pass `harness=`, `required_symbols=` and
`retained_symbols=` to `environment`, then use the same command-flag and
provenance helpers. Production and diagnostic harnesses retain separate recipes
and admission; removing diagnostic code is application savings.

## Replay the immutable111+5 diagnostic matrix

```text
python tools/validate_v5_runtime.py --study PRIVATE_JOINT_STUDY --source SOURCE_SNAPSHOT --output build/diagnostic --avr-bin AVR_BIN --runner FULL_RUNNER --lib SIM_LIB --wsl Ubuntu
```

The input study's saved111normal+5stress jobs define the exact ordered streams
and stress choices. The driver verifies all current files and independent-model
PWM against frozen complete output, then validates the supplied immutable source
snapshot with full duration coverage. It guards source/toolchain/validator and
manifest changes, saves private per-image evidence separately, and exports only
anonymous numeric rows and source/toolchain provenance under `public/`.
`--limit` explicitly creates a partial smoke report; it never marks the116-image
matrix complete. Preserve this same inventory when comparing the fixed baseline
with a candidate. The old capped duration totals are not a timing baseline.
