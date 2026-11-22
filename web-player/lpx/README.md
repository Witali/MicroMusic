# LPX V9 browser player and converter

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
supported audio, without DRM. OfflineAudioContext actually resamples to the
selected 8/12/16 kHz. Channels are averaged to mono and rounded/saturated to
PCM16 without gain normalization. Encoding runs in a cancellable Worker.

The entire recording is encoded in a single pass with continuous pitch history,
LPC interpolation and output-filter state. Standard 13-byte V9 is retained for
up to 64000 samples; longer recordings get one 17-byte V9 Long header and one
continuous payload. The result is one .lpx download and one playable recording.
[The Long specification](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/LPX9_LONG_FORMAT.md)
defines the marker and uint32 lengths. Existing AVR players reject Long;
ordinary V9 remains compatible with their previous limits.

P4/P6 use a C++/WASM port of speech_v4.py, wav_lpc.py, q0_model.py,
speech_compact.py and speech_v9.py. This is the scalar Hamming/autocorrelation/
Levinson/LSF and closed-loop integer pulse/scale/pitch search, with bandwidth
.97 and pre-emphasis 13926. It does not claim the quality of later offline
multi-pass optimizers. LPX is lossy and intended for speech; music may degrade.
Every complete emitted file is decoded through the shared C core and checked
sample by sample against the encoder's model, including strict final EOF.

The search stops losing candidates once their accumulated squared error reaches
the incumbent error, and skips later scale codes with the same integer step or
a repeated pitch gain. Candidate order, first-winner ties, winning-state replay,
wire packing and complete C validation remain unchanged. The differential suite
compares complete LPX bytes and PCM with the shipped exhaustive WASM at commit
688fc4f6, including V9 Long, clipping, silent ties and partial packets.

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

Build and check an explicitly selectable exhaustive C oracle with both
`LPX_ENCODER_ENABLE_PRUNING=0` and `LPX_ENCODER_DEDUP_CANDIDATES=0`:

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder
$env:LPX_EXHAUSTIVE_WASM = (Resolve-Path build/lpx-encoder-exhaustive.wasm).Path
node --test web-player/tests/lpx-encoder-exact.test.mjs
node web-player/scripts/benchmark-lpx-encoder.mjs
```

The benchmark requires local FFmpeg and compares the old and current production
modules on identical PCM. It retains hashes, all paired timings and environment
metadata in `build/lpx-encoder-benchmark.json`. See the retained
[measurements and reproduction notes](../../research/web-encoder-exact-search-2026-11-22/README.md)
and the [WASM optimization cookbook](../../docs/wasm-asm-cookbook/README.md).

The PC command uses Node and the same C/WASM decoder; it refuses to overwrite an
existing output. build.json and encoder-build.json retain source/compiler/flag
provenance and binary hashes. Both modules have no host imports. Linear memory
grows from 256 KiB as needed, capped at 256 MiB for decoding and 1 GiB for
encoding. Application limits are 32 million samples and 100 MiB of input;
browser audio and copied PCM require additional memory. Allocation failures
are reported, and recordings are never silently truncated.

Tests cover all retained streams/rates/profiles, short byte-exact regressions,
continuous old-limit crossings, uint32 payload lengths, corrupted EOF/padding,
allocation bounds and exact WAV export. Optional LPX_WSL_REFERENCE and
LPX_LEGACY_REFERENCE drivers compare full native C/WASM PCM and validate the
strict default build. Build tests/helpers/lpx-browser-reference.cpp with the
active core and matching LPX defines; only the wide driver enables the Long
flag. No new AVR timing or IRQ support is claimed.

The private Site exports only application assets and its hosting manifest,
without enclosing repository history, recordings or temporary test data.
