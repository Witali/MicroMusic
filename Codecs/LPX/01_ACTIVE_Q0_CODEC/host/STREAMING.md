# Continuous offline encoding

`LpxStreaming` shares the production C++ seed/search, synthesis, quality and
packing code with the native and scalar/SIMD WASM builds. Python is not a runtime
dependency. The wire format and MCU decoder are unchanged.

The WebUI processing selector is separate from its Auto/ordinary/SIMD backend:

- Auto retains full adaptive search through 128000 samples and selects fast
  streaming above that length.
- Fast streaming uses the original admissible continuous control, without the
  expensive adaptive refinement stage.
- Streaming refinement searches bounded windows and admits the complete result
  against the complete continuous control using the existing native-rate quality
  objective and full-band/temporal guards.
- Full search retains the existing whole-recording adaptive pipeline.

Windowed refinement is a different search from whole-recording refinement.
Neither mode is claimed to be audibly better from metric scores alone. Streaming
does not add optional extra pulses; full search retains that option. P4/P6 size
allowances still apply to their original v5 complete control accounting before
V9 repacking. The 3/8 presets retain their complete final V9 file budgets at8k.

## State and packing

Non-final windows contain 20480 samples (a multiple of1280), with at most48 real
future samples. Seed analysis carries48 emphasized samples and145 residual
samples. Host context retains172 raw samples,8 preceding coefficient vectors,
the previous spectrum and complete synthesis state (LPC history, pitch ring,
de-emphasis). Header parameters are fixed after the first window. The partial
future at EOF is padded with the same virtual zeros as whole-input analysis.

`V9PacketWriter` retains the preceding spectrum and unfinished byte between
append calls. Only complete bytes are drained; padding is written once at EOF.
The final known payload size supplies one13-byte V9 or17-byte Long header.
There are no concatenated LPX files or synthesis resets. Control and refined
paths each have their own continuous context. If the refined path exceeds its
remaining budget, the entire original control is retained.

JavaScript transports input/output only. Before offering the download, the
independent production C++ decoder decodes every sample and checks exact equality
with encoder synthesis, including EOF and padding validation. A refined stream
then undergoes complete-output admission. A specifically identified allocation
failure in that final gate retains the already completely decoded control;
other failures remain errors. Cancellation terminates the dedicated worker.

## Loudness and memory scope

Optional input normalization first measures the entire recording through the
shared incremental K-weighted gated meter. Its one peak-limited, boost-limited
gain is applied to every window and lookahead sample before encoding. Defaults
and short/below-gate behavior are unchanged. No gain field is written to LPX.

Model/search working storage is bounded by the window. This is not an unlimited
or constant-memory browser converter: the browser initially decodes the compressed
source into a whole AudioBuffer; output bytes, verification PCM and loudness
energy summaries still scale with duration. Streaming refinement's final complete
quality gate also requires whole PCM/analysis buffers. Existing100MiB source and
32million resampled-sample limits remain in force.

## Reproduction and evidence

Use the retained `build-lpx-wasm.mjs` and `build-lpx-native.mjs` build helpers.
Both include the same `LpxPacking.cpp` and `LpxStreaming.cpp`; WASM adds the
`enc_stream_*` transport API. Emscripten6.0.12/Clang24 and C++17 native builds use
`-ffp-contract=off`. Scalar C++ remains explicitly selectable on WASM and native;
existing native CPU/CUDA backend choices are preserved.

`web-player/tests/lpx-streaming.test.mjs` covers every profile, actual8/12/16kHz
normalization, native/scalar/SIMD equality, continued adaptive search, repeated
use, invalid states, whole-recording gain, exact decoded output and a simulated
final-gate allocation failure. `LPX_STREAM_NATIVE` points to the WSL build of
`tests/helpers/lpx-streaming-native.cpp`, linked with the production core and
all shared host units (excluding WASM/API entry-point files).

`tests/helpers/lpx-continuation-native.cpp` independently compares whole-input
seed output against continued seed and incremental packing: P4/P6,8/12/16kHz,
641/2561/20501/65537 samples (24 cases), including the short-lookahead EOF case.
Link it with LpxEncoder, LpxAdaptiveDsp, LpxPacking and Lpx4HybridCore. Enable
speech/compact, version9, extended rates, wide V9, integer synthesis and the C
fallback using the same build-helper defines.

The synthetic silent Long test compares65537 and1048577 samples. It requires
model WASM memory below32MiB and growth no greater than1MiB between lengths;
this assertion excludes browser AudioBuffer, JS output, decoder and final
quality-gate allocations. The real shipped Worker is also exercised through its
pull protocol, progress and cancellation tests. These are host correctness and
bounded-storage observations, not MCU timing or real-time support claims.
