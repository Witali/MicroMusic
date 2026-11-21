# LPX V9 browser player

Open `http://127.0.0.1:8133/web-player/lpx/` after running
`node web-player/scripts/serve.mjs` from the repository root. No npm installation
or build is needed to use the retained WASM binary. Serve over HTTP(S), not `file:`.

Select or drop one LPX V9 file. Playback, pause, seek, loop, volume, speed,
waveform and PCM16 WAV export run locally. Imported files never leave the browser.
The player accepts `L9` streams with P4/P6 (including extra pulses) and Sparse80,
8/12/16 kHz, and 1–64000 samples. Unsupported legacy formats and malformed/trailing
payloads are rejected. WAV export retains the stored rate and decoded samples;
listening volume and speed do not change the export.

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
WebUI V9 file at all three rates in a single native process.

The `.openai/hosting.json` identity is for the separate private Site. Hosting
exports only the player assets into `dist/`, without repository history,
recordings, imported audio, test outputs or build tools.
