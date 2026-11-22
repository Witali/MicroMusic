# Exact LPX V9 web encoder search, 2026-11-22

Implemented only nonnegative-loss pruning and removal of duplicate integer
scale steps / repeated gain 14. Candidate order and first-winner ties remain
unchanged. Winning pulses and blocks are replayed fully. Every complete encode
still runs the shared C decoder and checks all PCM samples and strict EOF.

## Measured whole-encode speed

Local Windows x64, AMD Ryzen 5 5600X, Node 22.22.3 / V8 12.4.254.21-node.56.
Both WASM builds use the same Clang 24 from Emscripten SDK 6.0.12, scalar `-O3`
and the same C decoder. Baseline is the shipped module at commit
`688fc4f618f9ed6176501e0f5d6e55bcb8fc80cf` (42851 bytes); optimized is 43198
bytes. Full SHA-256 values, flags, source hashes and individual runs are in
[measurements.json](measurements.json).

Each case first checks complete LPX bytes and externally decoded PCM. Then two
warmups and five paired runs alternate execution order. The table gives median
milliseconds for the whole synchronous JS encoder call: allocation/input copy,
LPC analysis, search, packing, complete C model verification, and output copy.
Assertions and the external decode are outside timing; internal C verification
is inside. No benchmark or test runs concurrently with another benchmark.

| Workload | Profile | Rate | Before, ms | After, ms | Speedup |
| --- | --- | --- | ---: | ---: | ---: |
| chego speech, 1.229 s | P4 | 8 kHz | 66.79 | 41.35 | 1.61x |
| chego speech, 1.229 s | P6 | 8 kHz | 554.95 | 328.68 | 1.69x |
| vinni speech, 2.970 s | P4 | 8 kHz | 162.48 | 113.20 | 1.44x |
| vinni speech, 2.970 s | P6 | 8 kHz | 1363.44 | 926.44 | 1.47x |
| chego speech | P4 | 12 kHz | 101.96 | 82.13 | 1.24x |
| chego speech | P6 | 12 kHz | 844.90 | 657.30 | 1.29x |
| chego speech | P4 | 16 kHz | 133.89 | 80.14 | 1.67x |
| chego speech | P6 | 16 kHz | 1119.77 | 610.69 | 1.83x |
| Two-tone, 1 s | P4 | 8 kHz | 57.98 | 32.60 | 1.78x |
| Two-tone, 1 s | P6 | 8 kHz | 452.27 | 232.53 | 1.94x |
| Silence, 2 s | P4 | 8 kHz | 19.52 | 16.15 | 1.21x |
| Silence, 2 s | P6 | 8 kHz | 54.63 | 21.74 | 2.51x |
| Two-tone Long, 65537 samples | P4 | 8 kHz | 436.88 | 246.08 | 1.78x |
| Two-tone Long, 65537 samples | P6 | 8 kHz | 3625.21 | 1800.84 | 2.01x |

All 14 cases have identical complete LPX and decoded PCM hashes. Speech inputs
are existing repository WAVs decoded/resampled by local FFmpeg; synthetic
generators, exact commands and PCM hashes are recorded. Audio is not uploaded.
These are host V8 measurements; no universal browser/CPU multiplier, memory
reduction or AVR timing/interrupt support is claimed. The binary grows by 347
bytes (0.81%); the workspace allocation and limits stay the same.

## Correctness and reproduction

The full LPX suite passed **62/62 tests, zero skipped**, with the native WSL C
reference and strict legacy reference enabled. The new differential suite runs
81 input/profile/rate combinations against the pinned old encoder and a newly
compiled exhaustive C fallback, including silence/tiny ties, noise, impulses,
full-scale/clipping, all packet/block tails, decoded speech, continuous Long
crossings and a payload above 65535 bytes. That fallback's WASM SHA-256 is
identical to the shipped baseline binary. The decoder source and binary are
unchanged. Browser QA additionally converted 8.2 seconds of stereo WAV to one
P6/8 kHz V9 Long file, then decoded and played its full duration without errors.

From the repository root, with Node, Git, the pinned SDK and FFmpeg installed:

```powershell
node web-player/scripts/build-lpx-wasm.mjs --emsdk C:/path/to/emsdk --reference-encoder
$env:LPX_EXHAUSTIVE_WASM = (Resolve-Path build/lpx-encoder-exhaustive.wasm).Path
node --test web-player/tests/lpx-encoder-exact.test.mjs
node web-player/scripts/benchmark-lpx-encoder.mjs --output build/repeated-benchmark.json
```

Optional native decoder drivers and their defines are described in the
[player README](../../web-player/lpx/README.md). To rerun the full LPX suite:

```powershell
# Set LPX_WSL_REFERENCE and LPX_LEGACY_REFERENCE to the wide/strict Linux drivers.
$lpxTests = Get-ChildItem web-player/tests/lpx-*.test.mjs | ForEach-Object FullName
node --test $lpxTests
```

The mathematical equivalence and portable fallback constraints are retained in
the [WASM cookbook](../../docs/wasm-asm-cookbook/README.md).
