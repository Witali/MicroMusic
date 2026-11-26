# LPX V9 browser player and converter

The published Web UI is
**[GitHub Pages](https://witali.github.io/MicroMusic/web-player/lpx/)**,
served from `web-player/lpx/` in the `main` branch of `Witali/MicroMusic`.
To update it, commit the application and matching WASM/build manifests, merge
into `main`, push `main` to `origin`, and verify that the live assets match the
commit. The tracked files are the production source; the optional
`export-lpx-site.mjs` script only creates a standalone static bundle.

Run `node web-player/scripts/serve.mjs` from the repository root and open
`http://127.0.0.1:8133/web-player/lpx/`. The retained WASM modules need no npm
installation or build. Use HTTP(S), not file URLs.

Select or drop one LPX file. Playback, seek, loop, volume, speed and PCM16 WAV
export run locally; imported audio never leaves the browser. The player accepts
standard V9 and the opt-in V9 Long Web/PC extension at 8/12/16 kHz, with P4/P6
(including extra pulses) and Sparse80. WAV retains decoded samples and rate;
listening speed and volume do not change it.

## One audio recording → one LPX file

The converter accepts browser-decodable WAV, MP3, FLAC, OGG, M4A/AAC and other
supported audio, without DRM. MP3, ordinary AAC/M4A and PCM16 WAV are decoded
in portions and resampled by the shared FIR; other formats use Web Audio.
The default is16 kHz, with8/12 kHz selectable. Channels are averaged to mono and rounded/saturated to
PCM16 with the source level preserved by default. **Нормализация громкости**
applies one constant gain to the entire PCM recording before encoding. Target
LUFS and maximum boost are adjustable; defaults are -18 LUFS and +12 dB. The
input sample-peak ceiling of -1 dBFS and boost cap may prevent reaching the
target. The result shows applied gain, prepared LUFS and decoded LPX LUFS.
The output uses ordinary V9/Long with no gain metadata; existing decoders and
WAV export receive the already normalized signal. Lossy coding may change its
final loudness. Short/below-gate recordings retain their input level. See
[normalization details](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LOUDNESS.md).
Encoding runs in a cancellable Worker.

The profile selector offers **P3/P4/P6/P8**, four allocations of the same
accuracy encoder. All use common analysis, safety recovery and residual-detail
proposals. Larger budgets can admit additional parameters; final decoded quality
and complete packed size decide admission. Levels are approximate speech-rate
targets at8 kHz, not strict complete-file bitrate limits. Higher sample rates
usually cost more bytes. P3/P4 retain the existing P4 wire alphabet and P6/P8
the P6 alphabet; packets are not literal truncatable bit-prefix layers.
See [allocation and quality rules](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/ACCURACY.md).
Explicit legacy APIs retain strict3/8 kbit/s modes and their byte contracts.

**Оценка качества** selects `PCM + ШИМ AVR` (the existing default) or
`Только PCM · компьютер / I2S / ЦАП`. PCM mode chooses and admits parameters
using decoded PCM, without the modeled AVR PWM constraints. The choice applies
to both ordinary/SIMD backends and full/streamed processing. LPX syntax and
playback are independent of the encoding target; no target marker is added to
the file. See [quality target APIs and validation](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/QUALITY_TARGET.md).

The entire recording is encoded with continuous pitch history,
LPC interpolation and output-filter state. Standard 13-byte V9 is retained for
up to 64000 samples; longer recordings get one 17-byte V9 Long header and one
continuous payload. The result is one .lpx download and one playable recording.
[The Long specification](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/LPX9_LONG_FORMAT.md)
defines the marker and uint32 lengths. Existing AVR players reject Long;
ordinary V9 remains compatible with their previous limits.

The processing selector offers Auto, fast streaming, streaming refinement and
full search independently of the ordinary/SIMD backend selector. Auto uses fast
streaming above128000 resampled samples. Streaming pulls20480-sample windows,
carries analysis/synthesis state and unfinished output bits, and checks the
entire decoded output before offering one file. Refinement keeps the original
continuous control and requires a complete-output quality admission. Its search
differs from full search and can take much longer than fast streaming.

Supported MP3/AAC/PCM16 WAV input and verification PCM use temporary local
storage; other formats use a whole browser AudioBuffer. Output storage also
scales with duration; streaming refinement's final quality gate needs full PCM
buffers. Fast accuracy streaming supports64 million samples; full search and
streaming refinement support32 million. Input files remain capped at100 MiB.
See [streaming design, memory scope and validation](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/STREAMING.md).

The shared encoder builds on a C++/WASM port of speech_v4.py, wav_lpc.py, q0_model.py,
speech_compact.py and speech_v9.py. This is the scalar Hamming/autocorrelation/
Levinson/LSF and closed-loop integer pulse/scale/pitch search, with bandwidth
.97 and pre-emphasis13926. Accuracy mode validates actual interpolated Q12
predictors and rendered level growth; a shared localized recovery handles
unsafe models without resetting continuous history. Additional detail is
admitted under the same source-quality guards at all levels. LPX remains lossy
and optimized for speech; music can degrade. At8 kHz source content above4 kHz
is removed before encoding. The16 kHz default retains more bright partials,
but does not preserve content above8 kHz.
Quality within the selected bandwidth is compared with the source prepared at
that same rate, without fitted gain or delay. Legal source partials, attacks,
decay and level remain fidelity targets; removing out-of-band source content
does not excuse replacing in-band sound with an unrelated tone.
Every complete emitted file is decoded through the shared C core and checked
sample by sample against the encoder's model, including strict final EOF.

### Ordinary and SIMD encoding

The page offers Auto, Ordinary and SIMD. Auto validates basic WebAssembly SIMD
support and selects the four-candidate SIMD search when available. It falls
back to ordinary C/WASM if the SIMD module cannot load or instantiate. Explicit
SIMD selection reports an error instead of silently changing mode; unsupported
browsers disable that option. Encoding/model failures always remain errors.
Results show the actual backend and synchronous encoding time, excluding
module loading and audio decoding/resampling. Both modes produce identical LPX.

The SIMD kernel evaluates independent amplitudes in four integer lanes, with
two pairs of double-precision loss lanes. It preserves per-candidate arithmetic,
strict tie order and complete scalar winner replay. `LPX_ENCODER_SIMD_SEARCH=0`
is the default portable backend; the SIMD artifact explicitly enables it with
`-msimd128`. Both modules are built by the normal build command. No threads or
cross-origin isolation headers are needed. See the retained
[kernel measurements](../../research/web-encoder-simd-search-2026-11-22/README.md).

The search stops losing candidates once their accumulated squared error reaches
the incumbent error, and skips later scale codes with the same integer step or
a repeated pitch gain. Candidate order, first-winner ties, winning-state replay,
wire packing and complete C validation remain unchanged. Shared pre-impulse
states let candidates resume at their pulse position; a 21520-byte static cache
retains complete filter/ring history, and winning trials still replay fully.
The differential suite
compares complete LPX bytes and PCM with the shipped exhaustive WASM at commit
688fc4f6, including V9 Long, clipping, silent ties and partial packets.
Strictly silent blocks directly commit the same winning pulses and ring state.
The fixed LSF grid and Hamming window cache exact double trigonometric terms
per instance; root bisection and scalar accumulation remain unchanged. The grid
adds 112816 bytes of static memory, prepared on the first encode.

## C/C++ → WebAssembly and PC use

The shared Lpx4HybridCore uses explicitly selected C arithmetic, with assembly
and floating synthesis disabled. LPX4_ENABLE_WIDE_V9=1 enables Long only in the
Web/PC build. Its default is zero; existing AVR layouts and bounded APIs remain
unchanged. The new beginWideV9(input, uint32 size) accepts both file headers.

Rebuild both modules with the existing SDK (read only):

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk
node --test web-player/tests/lpx-browser.test.mjs
node web-player/scripts/decode-lpx.mjs input.lpx new-output.wav
```

Build and check an explicitly selectable exhaustive C oracle with all five
optimizations disabled (`LPX_ENCODER_ENABLE_PRUNING`,
`LPX_ENCODER_DEDUP_CANDIDATES`, `LPX_ENCODER_REUSE_PREFIX`,
`LPX_ENCODER_FAST_SILENCE` and `LPX_ENCODER_CACHE_ANALYSIS` set to zero):

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder --prefix-selftest --analysis-selftest --simd-selftest
$env:LPX_EXHAUSTIVE_WASM = (Resolve-Path build/lpx-encoder-exhaustive.wasm).Path
$env:LPX_PREFIX_SELFTEST_WASM = (Resolve-Path build/lpx-prefix-selftest.wasm).Path
$env:LPX_ANALYSIS_SELFTEST_WASM = (Resolve-Path build/lpx-analysis-selftest.wasm).Path
$env:LPX_SIMD_SELFTEST_WASM = (Resolve-Path build/lpx-simd-selftest.wasm).Path
$lpxTests = Get-ChildItem web-player/tests/lpx-*.test.mjs | ForEach-Object FullName
node --test $lpxTests
node web-player/scripts/benchmark-lpx-encoder.mjs
```

The benchmark requires local FFmpeg and compares the old and current production
modules on identical PCM. It retains hashes, all paired timings and environment
metadata in `build/lpx-encoder-benchmark.json`. See the retained
[measurements and reproduction notes](../../research/web-encoder-exact-search-2026-11-22/README.md)
and the [WASM optimization cookbook](../../docs/wasm-asm-cookbook/README.md).
Use `--baseline 2a06935e` to measure prefix reuse relative to the shipped
pruning/deduplication build. The separate
[prefix measurements](../../research/web-encoder-prefix-search-2026-11-22/README.md)
retain that comparison. The direct compiled self-test exercises 918000
candidate/state/bound cases, including lag 18/19 feedback and ring wrap.
Use `--baseline 02a2fea5 --cold` to measure the silence/analysis changes after
items 1-3 and include first encodes in fresh instances. The retained
[analysis/backend experiments](../../research/web-encoder-analysis-cache-2026-11-22/README.md)
also cover exact grid math and the measured SIMD/compact-cache alternatives.
The explicit kernel adds 972000 lane/bound comparisons and backend selection,
unsupported-runtime and download/instantiation fallback checks. Set
`LPX_CANDIDATE_WASM` to `web-player/lpx/encoder-simd.wasm` and run
`lpx-encoder-exact.test.mjs` to compare all 87 stream cases with the shipped
exhaustive encoder. Clear that variable before the regular suite.

The PC command uses Node and the same C/WASM decoder; it refuses to overwrite an
existing output. build.json and encoder-build.json retain source/compiler/flag
provenance and binary hashes. Both modules have no host imports. Linear memory
grows from 256 KiB as needed, capped at 256 MiB for decoding and 1 GiB for
encoding. Decoder and fast accuracy streaming support64 million samples;
whole-input/refined search retains32 million. Input is capped at100 MiB;
browser audio and copied PCM require additional memory. Allocation failures
are reported, and recordings are never silently truncated.

Tests cover all retained streams/rates/profiles, short byte-exact regressions,
continuous old-limit crossings, uint32 payload lengths, corrupted EOF/padding,
allocation bounds and exact WAV export. Optional LPX_WSL_REFERENCE and
LPX_LEGACY_REFERENCE drivers compare full native C/WASM PCM and validate the
strict default build. Build tests/helpers/lpx-browser-reference.cpp with the
active core and matching LPX defines; only the wide driver enables the Long
flag. No new AVR timing or IRQ support is claimed.

The optional standalone export contains application assets and licenses,
without repository history, recordings or temporary test data. No separate
hosting manifest is needed for the GitHub Pages publication.
