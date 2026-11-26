# Shared LPX native encoder

The PC executable and browser WASM compile the same C++ search, adaptive
controller, quality metrics, fixed integer model and V9 packing. Python is
needed only for the independent regression oracle, never for encoding here.
Accuracy levels P3/P4/P6/P8 and 8/12/16 kHz are supported. All levels use
the same production accuracy engine as the Web UI, with P4/P6 wire syntax.
Recordings over 64000 samples use one
continuous V9 Long stream; no reset-file segmentation is performed.

See [shared policies and context ownership](ENCODER_UNIFICATION.md) for the
precision/bitrate distinction, reusable seed, bounded evaluator cache and
common native/WASM build description.

Quality evaluation can target decoded PCM or the existing combined PCM/AVR PWM
objective. Use `--quality-target pcm` for computer, I2S or DAC playback;
`--quality-target pwm` retains the default. Accuracy, bitrate and file syntax
are independent of this choice. See [target semantics and APIs](QUALITY_TARGET.md).

## Build

Use an installed Clang or GCC compiler. Windows builds use Clang with the
Microsoft ABI, the Visual Studio CRT and linker. GNU attributes in the shared
decoder are retained; a broad compatibility macro is not injected into MCU
sources. The build helper reads installed toolchains without changing them.

```powershell
node web-player/scripts/build-lpx-native.mjs --compiler C:/path/to/clang++.exe --msvc "C:/path/to/Visual Studio"
node web-player/scripts/build-lpx-native.mjs --cuda --compiler C:/path/to/clang++.exe --msvc "C:/path/to/Visual Studio" --nvcc C:/path/to/nvcc.exe --arch sm_120
```

On Linux, `node web-player/scripts/build-lpx-native.mjs --compiler g++` builds
the CPU executable. Pass `--cuda --nvcc /path/to/nvcc --arch sm_120` to add CUDA.
Choose an architecture supported by the installed SDK and GPU. There is no
automatic SDK download. Generated objects, executables and source/binary hashes
stay in ignored `build/lpx-native/`.

CUDA builds retain explicit `--backend cpu`; they select CPU by default. CUDA
is enabled only by the build define and a runtime `--backend cuda` request.
An unavailable or failing GPU produces an error instead of silently switching
backends. Clang/GCC use `-ffp-contract=off`; CUDA uses `--fmad=false` and does
not enable fast math. The CUDA translation unit is compiled by NVCC; shared
host sources use the same compiler and floating-point flags as the CPU build.

## Encode a file

```powershell
node web-player/scripts/encode-lpx-native.mjs input.wav new-output.lpx --quality adaptive --backend cpu
node web-player/scripts/encode-lpx-native.mjs input.wav new-output-cuda.lpx --quality adaptive --backend cuda
node web-player/scripts/encode-lpx-native.mjs input.wav new-output-p4.lpx --profile 4
node web-player/scripts/encode-lpx-native.mjs input.wav new-output-p8.lpx --accuracy 8 --rate 16000
node web-player/scripts/encode-lpx-native.mjs input.wav new-output-larger.lpx --legacy --profile 6 --size-allowance 25
node web-player/scripts/encode-lpx-native.mjs reference.pcm new-reference-output.lpx --legacy --profile 6 --pcm --search reference
node web-player/scripts/encode-lpx-native.mjs reference.pcm new-output.lpx --pcm --rate 8000 --profile 6 --repeat 5
node web-player/scripts/encode-lpx-native.mjs input.wav normalized.lpx --normalize --target-lufs -18 --max-gain-db 12
node web-player/scripts/encode-lpx-native.mjs input.wav output-pcm.lpx --quality-target pcm
```

The Node wrapper uses FFmpeg/FFprobe for audio-file input. It explicitly averages
all channels, resamples to the selected rate, disables dithering and produces
PCM16. No gain normalization is applied by default. Its resampler differs from Web Audio
and the Python reference converter: compare encoders on the same prepared PCM
with `--pcm`, rather than attributing input-conversion differences to encoding.
The wrapper accepts Unicode filenames, refuses to overwrite an existing output,
and writes only after successful complete-stream verification. Cancellation or
encoding failure leaves no successful output file.

`--normalize` applies one constant gain to the complete mono PCM recording before
encoding. `--target-lufs -30..-9` and `--max-gain-db 0..24` default to -18 and 12.
Input sample peaks cap gain at -1 dBFS; the target can remain unreachable.
The output is ordinary LPX V9/Long with no stored gain word or decoder changes.
Lossy coding can change the resulting loudness. Omit `--normalize` for unchanged
level; it cannot be combined with pre-encoding `--auto-quiet`.

The default is `--accuracy 6`; `--profile 3|4|6|8` is an alias for the same
accuracy level. These are precision/detail budgets, not bitrate promises.
Every level uses the common analysis, quantization, safety checks and residual
detail allocation. `--quality adaptive` adds up to `--calls 0..4` refinement
calls (four by default); `--quality fast` uses zero refinement calls in this
same engine. `--rate 8000|12000|16000` and `--encoder path` are explicit.
Compare identical prepared PCM, accuracy level, rate, normalization and call
count when checking native/Web parity.

`--legacy --profile 4|6` explicitly selects the historical encoder for oracle
and benchmark compatibility. Its `--quality fast` is the original bounded
seed search. Legacy adaptive mode defaults to expanded search: four refinement
calls, bounded pitch/gain extension, LPC bandwidth alternatives, pairwise pulse
lookahead and bounded spectral/time pulse proposals. Its
[shared multi-metric objective](PROFILE_QUALITY.md) compares completely decoded
PCM and PWM under the same byte cap. Original noise is part of the reference;
spectral/time fidelity does not require identical noise samples.

`--search expanded|reference`, `--size-allowance 0..100`, `--max-bytes N`,
`--auto-quiet` and `--non-speech` require explicit `--legacy`, including when
passing a zero allowance or budget. `--search reference` selects the original
Python-reference adaptive search. A percentage allowance enlarges the legacy
control budget; zero is the default. The legacy byte budget uses the complete
v5 control accounting before lossless V9 repacking, rather than the shorter
V9 file size. An explicit budget overrides the percentage allowance. Additional
pulses must fit that budget; extra size does not promise audible improvement.
Legacy automatic quiet-input gain is opt-in and reported as a power-of-two
exponent. `--accuracy` cannot be combined with `--legacy`.
Input is limited to 32000000 samples and is never silently truncated.

The native executable also accepts raw mono signed PCM16 little-endian on stdin
and writes LPX bytes on stdout. On Windows, use the Node wrapper: older
PowerShell redirection can reinterpret binary output. Diagnostic JSON is written
only to stderr and does not contain filenames, recording hashes or speaker data.

## Repeated timing and checks

`--repeat 1..20` encodes the same PCM repeatedly in one process and checks every
complete output against the first. The JSON report includes backend setup time,
`encodingMs` for the first encode, `repeatTimesMs` for every repetition, and
`warmMedianMs` (null without warm repetitions). The report also identifies
`engine` (`accuracy` or `legacy`) and `accuracyLevel`. Production mode reports
`search: "accuracy"`; legacy mode reports its search, `sizeAllowancePercent`
and the extension's local `expandedAccepted` count. That count alone is not a
claim that the selected file sounds better.
Encoding timings include shared
search, allocation, packing and native output verification; they exclude input
reading/conversion, GPU setup and process startup. Report end-to-end wall time
as well when comparing short files. Repeated output is emitted only once.

```powershell
node --test web-player/tests/lpx-common-cli.test.mjs web-player/tests/lpx-native-cli.test.mjs
```

These tests use built executables when present; `LPX_NATIVE_ENCODER` and
`LPX_CUDA_ENCODER` can select others. Common CLI tests compare all four accuracy
levels and all three rates with scalar/SIMD WASM and native CPU/CUDA. Legacy
tests explicitly use `--legacy` to preserve the historical reference/expanded
comparisons, including a 25% size allowance. Together they check repetition,
invalid input,
continuous V9 Long, binary-safe file writing, no-overwrite and channel averaging.
No real-time MCU or audible-quality claim follows from these host checks.
