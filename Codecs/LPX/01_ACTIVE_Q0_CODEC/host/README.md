# Shared LPX native encoder

The PC executable and browser WASM compile the same C++ search, adaptive
controller, quality metrics, fixed integer model and V9 packing. Python is
needed only for the independent regression oracle, never for encoding here.
P4/P6 and 8/12/16 kHz are supported. Recordings over 64000 samples use one
continuous V9 Long stream; no reset-file segmentation is performed.

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
node web-player/scripts/encode-lpx-native.mjs input.wav new-output-larger.lpx --size-allowance 25
node web-player/scripts/encode-lpx-native.mjs reference.pcm new-reference-output.lpx --pcm --search reference
node web-player/scripts/encode-lpx-native.mjs reference.pcm new-output.lpx --pcm --rate 8000 --profile 6 --repeat 5
node web-player/scripts/encode-lpx-native.mjs input.wav normalized.lpx --normalize --target-lufs -18 --max-gain-db 12
```

The Node wrapper uses FFmpeg/FFprobe for audio-file input. It explicitly averages
all channels, resamples to the selected rate, disables dithering and produces
PCM16. No gain normalization is applied by default. Its resampler differs from Web Audio
and the Python reference converter: compare encoders on the same prepared PCM
with `--pcm`, rather than attributing input-conversion differences to encoding.
The wrapper accepts Unicode filenames, refuses to overwrite an existing output,
and writes only after successful complete-stream verification. Cancellation or
encoding failure leaves no successful output file.

`--normalize` measures the completed decoded file and stores one constant output
coefficient in the optional [V9 gain extension](../LPX9_GAIN_FORMAT.md). It does
not change the input or refit the coded payload. `--target-lufs -30..-9` and
`--max-gain-db 0..24` default to -18 and 12; decoded sample peaks cap gain at
-1 dBFS. The target can remain unreachable. The updated decoder honors the word
in Web playback, WAV export and MCU output; older readers reject marked files.
Omit `--normalize` for unchanged level. It cannot be combined with pre-encoding
`--auto-quiet`. No reaction-time setting applies to a whole-file coefficient.

`--quality adaptive` uses the same expanded search as the Web UI by default:
four adaptive refinement calls followed by the bounded pitch/gain extension.
It then retains that complete result while testing LPC bandwidth alternatives,
pairwise pulse lookahead and bounded native-rate spectral/time pulse proposals.
Their [shared multi-metric objective](PROFILE_QUALITY.md) compares completely
decoded PCM and PWM under the same byte cap. Original noise is part of the
reference; spectral/time fidelity does not require identical noise samples.
`--search reference` selects the original Python-reference adaptive search;
`--search expanded` explicitly selects the default. Compare identical PCM,
profile, rate, level, call count and size allowance when checking PC/Web parity.
`--quality fast` is the unchanged original bounded seed search. `--profile 4|6`,
`--rate 8000|12000|16000` and `--encoder path` are explicit. Adaptive-only options
are `--calls 0..4`, `--search expanded|reference`, `--size-allowance 0..100`,
`--max-bytes N`, `--auto-quiet` and `--non-speech`. A percentage allowance
enlarges the original control budget; zero is the default. The default
byte budget is the complete v5 control size before lossless V9 repacking; an
explicit budget uses that same accounting, rather than the shorter V9 file size,
and overrides the percentage allowance. This permits additional pulses only
within the declared budget; it does not promise audible improvement.
Automatic quiet-input gain is opt-in and reported as a power-of-two exponent.
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
`search`, `sizeAllowancePercent` and the extension's local `expandedAccepted`
count; that count alone is not a claim that the selected file sounds better.
Encoding timings include shared
search, allocation, packing and native output verification; they exclude input
reading/conversion, GPU setup and process startup. Report end-to-end wall time
as well when comparing short files. Repeated output is emitted only once.

```powershell
node --test web-player/tests/lpx-native-cli.test.mjs
```

These tests use built executables when present; `LPX_NATIVE_ENCODER` and
`LPX_CUDA_ENCODER` can select others. They compare fast/adaptive native output
with reference and expanded WASM (including a 25% size allowance), explicitly
select CPU and CUDA, check repetition, invalid input,
continuous V9 Long, binary-safe file writing, no-overwrite and channel averaging.
No real-time MCU or audible-quality claim follows from these host checks.
