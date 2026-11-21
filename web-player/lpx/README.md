# LPX V9 browser player and converter

Open `http://127.0.0.1:8133/web-player/lpx/` after running
`node web-player/scripts/serve.mjs` from the repository root. No npm installation
or build is needed to use the retained WASM binary. Serve over HTTP(S), not `file:`.

Select or drop one LPX V9 file. Playback, pause, seek, loop, volume, speed,
waveform and PCM16 WAV export run locally. Imported files never leave the browser.
The player accepts `L9` streams with P4/P6 (including extra pulses) and Sparse80,
8/12/16 kHz, and 1–64000 samples. Unsupported legacy formats and malformed/trailing
payloads are rejected. WAV export retains the stored rate and decoded samples;
listening volume and speed do not change the export.

## Audio → LPX V9

The converter accepts browser-decodable audio (including WAV, MP3, FLAC, OGG,
M4A/AAC where supported). `OfflineAudioContext.decodeAudioData` actually resamples
to the selected 8/12/16 kHz. Channels are averaged to mono, rounded/saturated to
PCM16, with no gain normalization. Input size is limited to 100 MiB; decoding
still depends on browser memory and installed codec support. DRM is unsupported.

P4 and P6 use a separate import-free C++/WASM encoder ported from the active
project's `speech_v4.py`, `wav_lpc.py`, `q0_model.py`, `speech_compact.py` and
`speech_v9.py`. This retains Hamming/autocorrelation/Levinson/LSF analysis and
closed-loop integer pulse, scale and pitch search, with bandwidth .97 and
pre-emphasis 13926. It is the scalar baseline search, not the later offline
multi-pass quality optimizers. No compression-quality equivalence with those
optimized corpus encodes is claimed. P4/P6 are lossy speech profiles; music may
degrade. The unchanged C decoder validates both exact model PCM and strict EOF
for every emitted stream before it can be downloaded. The module has 2 MiB of
bounded linear memory; original/decoded audio uses additional browser memory.

Long audio is split at 64000 samples without dropping or duplicating samples.
Each segment resets decoder state; boundaries may be audible. Results can be
previewed individually, downloaded separately, or saved in an uncompressed ZIP
with ordered `playlist.json`. The ZIP writer runs locally and has no dependency.
Encoding runs in a cancellable Worker with progress. `encoder-build.json`
records the port, upstream algorithm provenance, compiler and source/binary
hashes. The shared build script rebuilds both decoder and encoder modules.

## C/C++ → WebAssembly

The small `native/decoder.cpp` ABI compiles the existing, unmodified
`Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp` portable C arithmetic
backend. Assembly and floating synthesis are explicitly disabled. No Javascript
DSP translation, AVR emulation or third-party runtime is needed. A module Worker
keeps decoding off the UI thread. HTML audio plays the resulting PCM16 WAV.

Rebuild with the existing Emscripten SDK (read only):

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk
node --test web-player/tests/lpx-browser.test.mjs
```

`build.json` records compiler, flags, source hashes, binary hash and the bounded
256 KiB linear memory. See the active codec's `LPX9_FORMAT.md` for wire details.
The native differential test can additionally use `LPX_WSL_REFERENCE` pointing
to a Linux executable built from `tests/helpers/lpx-browser-reference.cpp` and
the active core with the same LPX feature defines. It compares every retained
WebUI V9 file at all three rates plus generated P4/P6 tails, full-size silence
and re-encoded speech in a single native process. Other tests cover malformed
input, exact WAV export, encoder model agreement and ZIP directory layout.

The `.openai/hosting.json` identity is for the separate private Site. Hosting
exports only the player assets into `dist/`, without repository history,
recordings, imported audio, test outputs or build tools.
