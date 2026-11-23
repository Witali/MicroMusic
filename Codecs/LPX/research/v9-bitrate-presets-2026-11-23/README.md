# Shared LPX V9 presets at 3 and 8 kbit/s

The browser converter and PC CLI now offer two complete-file bitrate ceilings.
Both use the existing `L9` format and unchanged universal decoder. No wire
profile 3 or 8 is introduced: the encoder emits P4 or P6, optionally with the
existing extra-pulse flag. The shared native C++ and scalar/SIMD WASM code is
the runtime implementation; Python remains an independent legacy oracle.

## Preset contract

Both presets currently require 8000 Hz. The strict byte cap is
`floor(samples * kbps * 1000 / (8 * 8000))`, including the whole header,
packet padding and partial final packet. Ordinary P4/P6 retain their old
rate/allowance controls. The new presets reject nonzero size allowances.
Short and Long files retain one continuous synthesis state, actual sample
count, and the existing 13/17-byte V9 headers. There are no inserted resets,
silent truncation, playback-rate changes or filler bytes.

- **3 kbit/s:** existing P4 seeds, energy-weighted adjacent spectral merges,
  bounded uniform controls and exact scale/lag/gain/innovation fitting.
  The final serialized file is the size authority. If ordinary plans cannot
  fit, an explicit zero-gain search exploits V9's omitted zero-gain lag field.
  A failed bounded search returns no-fit; it is not a global infeasibility proof.
- **8 kbit/s:** the current shared adaptive P6 search and existing budgeted
  extra pulses. Internal operators use complete v5 accounting, so their cap
  is adjusted for the guaranteed V9 header saving and checked again on the
  actual final V9 bytes. Easy inputs may use much less than the ceiling.

The 3 kbit/s C++ search shares the accepted low-rate mechanisms, not every
candidate of the older Python encoder. Its shared seed analysis uses bandwidth
`.97` and bounded doubling uniform cadences. Whole-output PCM/PWM error, STOI,
period-count and clipping guards protect its control; no subjective quality
guarantee follows from them.

Previously selected v5 3 kbit/s files retain the independent lossless repacking
path in `tools/speech_v9.py`. On the retained tuning phrase, all 19,200 PCM16
samples of that path match the legacy model; 900 bytes become 882 bytes.
Re-encoding its source is a separate bounded search. Legacy v2/v3 LPX8 requires
re-encoding and is not embedded inside a V9 wrapper.

## Fixed public phrase

These are tuning diagnostics, not a heldout corpus or a listening verdict.
The same 2.4-second, 19,200-sample mono target is used without fitted output
gain. PWM SER is computed from summed reference/error energies.

| Variant | Complete bytes | PWM SER, dB | PWM STOI |
| --- | ---: | ---: | ---: |
| Retained historical 3k selection, losslessly repacked | 882 | 4.73555 | .75935 |
| New C++ 3k preset | 887 / cap 900 | 4.46037 | .76328 |
| New C++ 8k preset | 1480 / cap 2400 | 5.52379 | .79433 |

The new 3k result trades lower waveform SER for slightly higher STOI on this
phrase. It is not labelled an unconditional improvement over the retained
selection. The 8k result actually uses about 4.93 kbit/s. Existing audio
catalogs and previously selected streams are not replaced by these tests.

All four Tiny88/Mega complete-player checks pass with active interrupts,
76,800 exact PWM samples and zero underruns/errors. Full image sizes are
4516/5110 bytes on Tiny88 and 3904/4496 on ATmega328P. See [the full measured
recipe and limits](FIRMWARE.md) and [anonymous results](firmware.json).
This covers the fixed phrase, not every 8k candidate or a physical board.

## Validation and reproduction

Final focused browser checks passed: 19 tests cover preset caps, scalar/SIMD,
short fallback, silent Long, UI constraints, backend/worker, source provenance
and existing adaptive invariants. The earlier complete focused run also passed
all 27 executed tests, including ordinary P4/P6 byte-exact and continuous Long
regressions; two optional native-driver tests were skipped there.

The PC CLI's two tests pass, including PCM16 amplitude, malformed WAV,
complete file caps and exclusive output creation. A separate native test ran
both presets over five inputs each: short/nonaligned tones, quiet audio,
transitions and 65,537-sample continuous silence. Every complete file matched
both scalar and SIMD WASM exactly, passed the common C decoder and respected
its final byte cap. Legacy v5-to-V9 conversion was checked separately as above.

```text
node web-player/scripts/build-lpx-wasm.mjs --emsdk <emsdk>
node --test web-player/tests/lpx-bitrate-presets.test.mjs web-player/tests/lpx-bitrate-cli.test.mjs
node web-player/scripts/encode-lpx.mjs input-8khz.wav new-output.lpx --kbps 3
node web-player/scripts/encode-lpx.mjs input-8khz.wav another-output.lpx --kbps 8 --backend simd
```

The PC command accepts prepared mono PCM16/8000 Hz RIFF/WAV. The browser import
path handles its supported audio formats and actually resamples before
encoding. Existing destinations are refused. Both modes run the same C++ WASM.

For an independent native driver, compile the active core and host units
`LpxEncoder`, `LpxAdaptiveDsp`, `LpxQuality`, `LpxStoi`, `LpxRefinement`,
`LpxAdaptiveController`, `LpxAdaptiveApi`, `LpxBitrateProfiles`, and
`web-player/tests/helpers/lpx-bitrate-native.cpp` with C++11, `-O3`,
`-ffp-contract=off`, the source/host include directories, and:

```text
-DLPX_ADAPTIVE_ENCODER=1 -DLPX4_ENABLE_ASM=0 -DLPX4_FLOAT_SYNTHESIS=0
-DLPX4_ENABLE_SPEECH=1 -DLPX4_ENABLE_SPEECH_COMPACT=1
-DLPX4_COMPACT_ONLY=1 -DLPX4_COMPACT_VERSION=9 -DLPX4_SAMPLE_RATE=0
-DLPX4_EXTENDED_SAMPLE_RATES=1 -DLPX4_ENABLE_WIDE_V9=1
```

Set `LPX_BITRATE_NATIVE` to the resulting executable and run
`node --test web-player/tests/lpx-bitrate-native.test.mjs`. For a Linux helper
from Windows, set the path in WSL notation and `LPX_BITRATE_WSL` to the local
distribution. The measured native compiler was GCC 13.3.0; WASM uses the pinned
Emscripten 6.0.12/Clang 24 SDK with explicit scalar and SIMD builds. Build
manifests bind all inputs, flags and binaries. Raw media, source bindings,
firmware images and detailed private diagnostics remain in ignored `build/`.
