# Shared LPX V9 Web encoder validation

Validated on 23 November 2026. The browser now selects the shared C++ adaptive
pipeline, followed by the guarded expanded pitch/gain operator. Python is an
independent test oracle and is absent from both shipped WASM modules.

The reference ABI remains `enc_adaptive`; `enc_adaptive_extended` adds the
bounded search described in [EXPANDED_SEARCH.md](host/EXPANDED_SEARCH.md). Native
PC, ordinary WASM and SIMD WASM compile the same host sources. Input level is
preserved by default. Auto/ordinary/SIMD selection, local processing, P4/P6,
8/12/16 kHz, and one continuous V9/V9 Long output are retained. The page offers
zero, 10%, or 25% allowance over the original complete control budget before V9
repacking. The original admissible candidate remains available.

## Evidence

| Check | Result |
| --- | --- |
| Independent Python/native/WASM differential | 36/36 exact LPX bytes and complete decoded PCM |
| Anonymous local corpus windows | 227/227 native/ordinary/SIMD exact bytes and complete PCM; 222 distinct windows |
| Real audiobook Long excerpt | 128001 samples at 8 kHz; adaptive and expanded native/ordinary/SIMD agree; one 6539-byte file |
| Expanded-search native gates | 68/68 checks; 34 changed synthetic outputs; public speech retained its reference candidate |
| Node LPX regression suite | 78 passed; two conditional native checks subsequently passed in the 13/13 native-decoder run |
| Shipped worker integration | 1/1; default adaptive downloads, allowance forwarding, all three backend choices, full decode |
| WASM provenance and imports | Current normalized-source hashes; zero host imports |

The 36 differential cases comprise 22 synthetic edge cases, six full public
source/profile pairs, and eight private windows. They cover packet tails,
silence, clipping, quiet signals, noise and transitions. Additional tests cover
all three rates, explicit quiet gain, malformed requests, infeasible budgets,
stable heap size after warmup, repeated calls, and synthetic continuous Long
streams at 65537 and 131073 samples.

The 227 corpus cases use 3201-sample windows (0.400125 seconds), with four
reference refinement calls: 181 archived cases (91 P4, 90 P6) and 46 audiobook
windows (23 per profile). The archive contains 49 speech cases (27 Russian,
22 English) and 132 music cases. The audiobook windows span 21 source files;
these counts do not establish a number of independent speakers. Only the
separate 128001-sample excerpt establishes the real-audio Long check. Complete
audiobooks and the maximum 32-million-sample browser input were not validated.
Private recordings, titles, identifiers, paths, hashes and manifests are
excluded from published content.

The expanded Long proposals were rejected by complete-stream guards, retaining
the original. Numerical results do not establish audible improvement. Local
source/decoded A/B files for the three public clips were prepared separately
for listening. No subjective listening result is claimed. The offline metrics
follow the 8 kHz reference; retained 12/16 kHz choices have correctness coverage,
not a new perceptual-quality guarantee.

The background chat exposed no browser surface for visual QA. The actual worker,
asset loader, WASM modules, output bytes and decoder were exercised automatically;
no manual layout or browser audio-playback verification is claimed.

## Reproduction

WASM uses pinned Emscripten 6.0.12 / Clang 24, C++11, `-O3`,
`-ffp-contract=off`, and explicit scalar/SIMD builds. The build manifests retain
all flags and input hashes. From the checkout root:

```text
node web-player/scripts/build-lpx-wasm.mjs --emsdk <emsdk> --reference-encoder --prefix-selftest --analysis-selftest --simd-selftest
node --test web-player/tests/lpx-adaptive.test.mjs web-player/tests/lpx-worker.test.mjs
python web-player/scripts/check-lpx-adaptive.py
python web-player/scripts/check-lpx-expanded.py --encoder build/lpx-native-extended --full
```

The native helper was built on Ubuntu with GCC 13.3.0:

```sh
g++ -O3 -std=c++11 -ffp-contract=off \
  -DLPX_ADAPTIVE_ENCODER=1 -DLPX4_ENABLE_ASM=0 -DLPX4_FLOAT_SYNTHESIS=0 \
  -DLPX4_ENABLE_SPEECH=1 -DLPX4_ENABLE_SPEECH_COMPACT=1 \
  -DLPX4_COMPACT_ONLY=1 -DLPX4_COMPACT_VERSION=9 -DLPX4_SAMPLE_RATE=0 \
  -DLPX4_EXTENDED_SAMPLE_RATES=1 -DLPX4_ENABLE_WIDE_V9=1 \
  -ICodecs/LPX/01_ACTIVE_Q0_CODEC/src -ICodecs/LPX/01_ACTIVE_Q0_CODEC/host \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxEncoder.cpp \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxAdaptiveDsp.cpp \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxQuality.cpp \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxStoi.cpp \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxRefinement.cpp \
  Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxAdaptiveController.cpp \
  web-player/tests/helpers/lpx-native-encode.cpp -o build/lpx-native-extended
```

Set `LPX_EXHAUSTIVE_WASM`, `LPX_PREFIX_SELFTEST_WASM`,
`LPX_ANALYSIS_SELFTEST_WASM`, and `LPX_SIMD_SELFTEST_WASM` to the generated
`build/` helpers for the full Node suite. The two native decoder checks also use
`LPX_WSL_REFERENCE` and `LPX_LEGACY_REFERENCE`, built from
`web-player/tests/helpers/lpx-browser-reference.cpp` with wide V9 enabled and
disabled respectively. These are test-only executables, not website assets.

The C++ runtime initializer is explicitly exported and called once per WASM
instance. This corrects export-wrapper reinitialization of static containers;
tests inspect the signature, full decoded stream, report getters and reuse.
The SIMD kernel keeps its explicit enable flag and portable C++ fallback.
No AVR real-time, interrupt timing, new assembly, or CUDA claim follows from
this Web release. CUDA work continues separately.
