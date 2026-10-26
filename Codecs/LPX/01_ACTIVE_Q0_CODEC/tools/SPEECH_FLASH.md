# AVR program-Flash size profiles

These are explicit build recipes for ATmega328P/AVR5,16MHz,8kHz PWM,
AVR-GCC7.3.0. Encoded audio is unchanged. No new assembly or hardware
definitions are added. Keep all defines consistent across the core and its
consumers because format flags affect class layout.

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
