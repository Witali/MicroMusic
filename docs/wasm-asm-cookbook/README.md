# WebAssembly optimization cookbook

## Exact pruning and duplicate elimination in LPX V9 search

Measured scalar C++ implementation for `wasm32-unknown-unknown`, exported C ABI,
32-bit linear memory and double-precision loss. Emscripten SDK 6.0.12's Clang 24
with `-O3`, freestanding/no host imports; no SIMD, threads or handwritten assembly.
The techniques reduce search runtime. They do not reduce working memory or
change the shared decoder, firmware arithmetic, or real-time IRQ support.

The implementation is original project code in
[LpxEncoder.cpp](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxEncoder.cpp). It optimizes the existing
speech_v4 closed-loop search; it does not adapt external assembly.

### Stop candidates that cannot win

Accumulate squared PCM error in the original order. Each term is nonnegative,
and a whole 160-sample block has integer error at most `160 * 65535^2 < 2^40`,
exactly representable in a double. Once `loss >= incumbent`, later samples cannot
make that candidate win the existing strict `<` comparison. Use the current
20-sample pulse incumbent inside a trial and the block incumbent between
subframes. Discard every aborted trial's partial filter/ring state.

Replay each winning pulse fully to produce the next subframe state. Replay the
winning block fully to commit pulses, expected PCM and state. Both replays use
an infinite bound. Do not reorder candidates, change the tie comparison, or
reuse a partial state as a winner. Analysis, rounding and packing are unchanged.

### Eliminate equivalent candidates while retaining their first wire code

Several allowed scale codes map to the same `steps[scale * 8]`. At the same
initial state, lag and gain, they run identical arithmetic and select identical
pulses/history. Skip a scale only when an earlier *admitted* scale has the same
step. Retain the first code because its wire representation wins equal errors.
The incumbent only decreases, so an earlier bounded rejection remains a loser
when an equivalent candidate appears later. When estimated pitch gain is 14,
the later fixed-gain-14 candidate is also redundant.

Do not equate zero-step candidates with different gains: they can store different
ring histories even when the current audible output is zero. Do not replace
equal output with a different encoded scale/pulse representation.

### Reuse the exact state before a pulse

For each subframe/scale/gain, run a zero-impulse trial once and cache the state
and cumulative loss immediately before each of its 20 sample positions. A
candidate at position `pos` has the same prefix, so clone that snapshot and
continue the unchanged synthesis/error loop at `pos`. If the cached prefix
already reaches the incumbent loss, discard the candidate before copying it.
Winner replay still starts from the original state and writes every PCM sample.

Snapshots include all ten LPC history values, de-emphasis state and the complete
256-entry excitation ring. In particular, lags 18/19 can read excitation already
generated in the same subframe; cloning only filter history would be incorrect.
Build a fresh cache for every subframe/scale/gain and preserve candidate order.
The loss is the same exact integer-valued double prefix sum; no sum is reordered.

This scalar wasm32 implementation adds `20 * (267 * 4 + 8) = 21520` bytes of
static cache per encoder instance, plus alignment. Keeping the cache outside the
32 KiB stack avoids a large stack frame. The encoder already owns mutable state
per WASM instance; instances do not share this cache. Limits and workspace
buffers are unchanged. `LPX_ENCODER_REUSE_PREFIX=0` selects the original C trial
on this architecture; no assembly, SIMD or browser isolation changes are needed.

The [prefix experiment](../../research/web-encoder-prefix-search-2026-11-22/README.md)
records additional speed relative to the already pruned/deduplicated encoder,
not relative to the original exhaustive version. A dedicated compiled harness
checks 918000 state/loss/bound cases, including lags 18/19, ring wrap, all pulse
positions/amplitudes, saturation and exact ties. Full-stream differential tests
and the shared-C decode/model validation remain enabled.

### Commit strictly silent blocks without searching

Keep the original guard: zero residual power, zero de-emphasis state and all
ten LPC history values zero. With scale zero and gain zero, every pulse
candidate synthesizes zero, so strict ties always select position zero and
amplitude -8. Write those eight pulses and 160 expected zero samples directly.
Overwrite only the block's 160 ring entries, preserving the other 96 entries;
do not erase excitation history. The guard and parameter packing are unchanged.
`LPX_ENCODER_FAST_SILENCE=0` selects the original search path.

The direct harness compares the complete resulting state/PCM/pulses at all eight
ring alignments, both profiles, and zero/tiny/full-scale sources. Stream tests
also cover leading silence, decay into a pause and resumed excitation. The
shortcut alone saves only 4-8% on the recorded silence workload after items 1-3;
analysis dominates its remaining runtime.

### Cache the exact fixed-grid trigonometric terms

The 641 LSF grid points (including the original `1e-6` starting point) and the
256-sample Hamming window are constant across frames/rates/profiles. Initialize
the original double `sin`/`cos` expressions once per WASM instance. Cache all
`2 * 641 * 11` terms and retain the original scalar multiply/add order for root
values. Keep bisection between grid points on the original trigonometric code;
use no recurrence, approximation or root interpolation.

The table consumes 112816 bytes plus alignment/ready state, generated at runtime
rather than embedded as a large download. The direct harness checks 20768
Hamming values, grid terms and root sums bit for bit, including cancellation.
`LPX_ENCODER_CACHE_ANALYSIS=0` selects per-call window preparation and direct
grid evaluation. The [analysis/cache experiment](../../research/web-encoder-analysis-cache-2026-11-22/README.md)
records first-encode and warm measurements, all output hashes and full checks.
The first-encode measurements matter because the browser creates a new Worker
for each conversion. This is an offline Web/PC optimization; existing firmware
timing support is not changed.

### Measured SIMD and compact-prefix alternatives

On the same scalar source, `-msimd128` gave 0.98-1.02x whole-encode ratios and
increased WASM from 43922 to 45670 bytes. A compact prefix cache reduced its
21520 bytes to 1120 bytes but slowed non-silent cases by approximately 23-45%.
Both passed the same direct state/math harnesses and 87-case stream suite. They
are reproducible experiments, not selected production backends. Keep the
simpler scalar/full-prefix implementation for these measured workloads; no
general claim about explicit SIMD kernels or other CPUs follows from this test.

### Evaluate independent pulse candidates in SIMD lanes

The [explicit four-candidate backend](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxEncoderSimd.h)
uses wasm32 SIMD128 intrinsics from the pinned Emscripten 6.0.12/Clang 24 SDK.
It is original project code; the compiler's LLVM header is included, not copied
or adapted. [Emscripten's SIMD reference](https://emscripten.org/docs/porting/simd.html)
documents the intrinsics and `-msimd128` target flag. No relaxed SIMD/fast math,
threads or handwritten assembly are used. Ordinary C remains explicitly
selectable, including on SIMD-capable hosts.

Map four amplitudes at the same pulse position to four i32 lanes, sharing the
cached prefix. Keep ten independent LPC histories and de-emphasis values in
vectors. Lags 18..145 mean only newly generated samples 0 and 1 can feed back
within a 20-sample trial; retain those two excitation vectors and read other
delays from the passed prefix ring. Loser state is never committed, so there
is no need to clone an entire scalar ring for every trial. Replay each winner
fully with the original scalar trial to commit pulses/state/PCM.

Each shifted coefficient product and clipped intermediate uses the same signed
32-bit arithmetic. Products and their sums fit under the existing bounded
states. Convert PCM differences exactly to two f64x2 pairs and accumulate the
squared loss per lane in original sample order. Per-trial integer loss remains
below 2^37, exactly representable as double. Never replace it with float loss or
reassociate a sum across samples.

A batch uses the incumbent bound from before its first lane. It may do more
work than sequential pruning, but a rejected lane cannot beat the subsequently
decreasing incumbent. Stop when all lanes reach the bound, then examine lanes
in original order using strict `<`. P4 uses two distinct amplitudes in duplicated
lanes; P6 uses four groups of four. Preserve zero-step ties and clipping.

`LPX_ENCODER_SIMD_SEARCH=1` selects this path only when `__wasm__`,
`__wasm_simd128__` and prefix reuse are enabled; other builds keep scalar C.
The C ABI and stream/model validation are unchanged. The web loader validates
SIMD support before selection, exposes explicit ordinary/SIMD modes, and limits
automatic fallback to loading/instantiation failures. It does not hide model
validation failures. [The retained kernel experiment](../../research/web-encoder-simd-search-2026-11-22/README.md)
records first/warm timings, flags, hashes, 972000 direct lane/bound comparisons
and complete byte/PCM comparisons for 87 stream cases. These measurements are
for local V8 workloads and do not establish performance on another CPU/browser.

### Fallback and evidence

`LPX_ENCODER_ENABLE_PRUNING=0`, `LPX_ENCODER_DEDUP_CANDIDATES=0`,
`LPX_ENCODER_REUSE_PREFIX=0`, `LPX_ENCODER_FAST_SILENCE=0` and
`LPX_ENCODER_CACHE_ANALYSIS=0` independently disable these techniques. Setting all
five to zero retains the exhaustive portable
C++ path on the same architecture. The build helper's `--reference-encoder`
produces this oracle separately from the production assets. Complete LPX/PCM
is checked against the pinned shipped exhaustive module. The experiments retain
exact binary hashes; C code layout changes can change the oracle's WASM hash.

[The retained experiment](../../research/web-encoder-exact-search-2026-11-22/README.md)
contains workloads, before/after timings, raw runs, compiler flags, hashes and
reproduction commands. Differential tests compare LPX bytes and decoded PCM
against the pinned pre-optimization module; every encode also performs the
unchanged full shared-C model validation and strict EOF check. These host V8
measurements do not establish another browser/CPU's speed or AVR audio timing.

### Shared adaptive C++ in a standalone WASM module

The LPX host pipeline compiles the same C++11 seed, integer synthesis, V9 packing,
quality metrics and refinement sources for native PC, scalar wasm32 and wasm32
SIMD128. The explicit SIMD define still selects only the existing supported
pulse kernel; ordinary C++ remains selectable on every host. These encoders run
offline and establish no interrupt-active real-time audio profile.

The freestanding Clang/wasm-ld build exports `__wasm_call_ctors`; its JavaScript
loader invokes it once immediately after instantiation. Without an explicit
initializer export, linker-generated export wrappers can initialize static C++
containers again before getters, clearing a previously generated output vector.
A positive encode length or equality of two output buffers cannot detect that
failure alone. The adaptive regression suite checks the `L9` signature, decodes
the entire output, checks getters, and exercises repeated calls with a stable
warmed heap. Construct memory views after the search because WASM memory may
grow during it. This is a validated correctness technique for this standalone
ABI and pinned Emscripten 6.0.12/Clang 24 build, not a performance claim or a
replacement for another runtime's startup protocol.

The [expanded-search notes](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/EXPANDED_SEARCH.md)
describe bounded pitch/gain proposals and full-stream quality/size guards.
Python remains an independent regression oracle; it is absent from the runtime.
## Two-pass metrics with frame rings

[The STOI buffer refactoring](../../Codecs/LPX/research/wasm-stoi-streaming-2026-11-23/README.md)
retains the global silence mask while processing resampling, overlap-add and
STFT/correlation through small rings. It preserves FIR/reduction ordering and
exclusive frame bounds; 48 native differential cases are bit-identical. In the
documented 64 MiB scalar WASM probe it avoids the original allocation trap and
uses about 29.2 MB including the unchanged seed workspace. This is portable C++11
with Emscripten6.0.12/LLVM24, no ISA extension or handwritten assembly; scalar
and SIMD builds share it. Caller PCM and energy summaries remain proportional
to input length. The linked evidence states the workload and limits.

## Continuous seed and packet state across windows

The [offline streaming encoder](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/STREAMING.md)
uses aligned20480-sample windows plus48-sample lookahead. Carry the raw,
pre-emphasized and residual history, preceding spectrum/coefficient interpolation,
LPC/pitch/de-emphasis state and partial output byte. Padding only at EOF avoids
both waveform resets and invalid per-window byte alignment. At a short final
lookahead, pre-emphasize the virtual-zero tail as whole-input analysis does.

This is shared portable C++, without handwritten assembly or ISA requirements;
scalar C remains explicitly selectable with native CPU and wasm32 SIMD builds.
The retained24-case native helper checks complete seed parameters, bytes and PCM
at8/12/16kHz against whole-input search. The Web tests compare scalar/SIMD/native
and independently decode every final sample. Model memory is window-bounded;
compressed-source browser decoding and final quality verification are not.
Pinned tools, synthetic memory assertions and reproduction details are linked
above. No AVR timing or speedup is inferred from these host checks.

## Precision policies and incremental verification

The [unified accuracy policy](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/ACCURACY.md)
shares C++11 LPC/excitation search, quantization and packet state between native,
scalar wasm32 and optional SIMD128. Quantize ordered LSF rank residuals rather
than independently pruning coefficient magnitudes, preserving strict LSF
ordering and stable synthesis constraints. Spend correction symbols according
to reconstructed error reduction per added bit, then count complete packed
bytes and evaluate whole output. A profile's own original seed remains
admissible; intermediate relative scores are not transitive and must not be
multiplied. This is an allocation/correctness technique, not a speed claim.

The verification decoder exports static C++ state with explicit one-time
`__wasm_call_ctors` startup, then retains synthesis/bitreader state across
20480-sample output reads. Arbitrary read sizes, strict EOF corruption and
repeated use match full decoding. This changes PCM working storage from a
whole recording to a window; the compressed LPX file remains resident.
The pinned Emscripten6.0.12/Clang24 standalone ABI has no imports or Python
runtime. These host memory checks establish no MCU timing profile.

## Backpressure without codec-state resets

The [bounded audio input](../../web-player/lpx/AUDIO_INPUT.md) uses WebCodecs
dequeue events to cap pending packets at eight, closes each AudioData, and
flushes only at true EOF. Repeated intermediate flushes lost AAC overlap/MP3
synthesis history in actual in-app browser checks; native-rate Web Audio versus
AudioDecoder comparisons with the same FIR then matched MP3/AAC exactly.
The shared portable C++ FIR retains rational phase and history in a fixed1 MiB
wasm32 module (Emscripten6.0.12/Clang24), independent of input packet boundaries.
Mono/stereo PCM and verification output go to a local OPFS file, leaving only
short views in JS/WASM. Native/WASM tests cover passband/alias response and exact
packet independence; this is a working-memory/correctness result, not an
architecture speedup. Scalar C++ is always selectable; no handwritten assembly
or additional ISA is required. Refined/global quality buffers remain separate.

## Reusing seed and candidate evaluation across search stages

The [encoder ownership and policy refactoring](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/ENCODER_UNIFICATION.md)
passes a prepared seed to the adaptive controller and shares actual-rate source
analysis across quality stages. Cache exact packet keys together with the
continuation flag, preceding LPC spectrum and full synthesis state. Equal wire
bytes can render differently at window boundaries. Bound both entry count and
retained key bytes; keep scalar metric summaries instead of every candidate PCM.
Each quality stage must retain its own frozen incumbent and denominator, while
the selected output still receives independent complete decoder verification.

`SeedEncoder` separates per-search buffers/state from shared immutable analysis
tables. Interleaving two seed contexts verifies ownership without assuming the
legacy default C ABI or the single CUDA stream is concurrent. These are portable
host C++11 techniques for wasm32 and native builds, using Emscripten6.0.12/Clang24
with strict floating-point contraction disabled. SIMD128 remains explicitly
selected; the same C++ fallback is available without it. No handwritten assembly
is introduced. [Paired results and reproduction](../../Codecs/LPX/research/encoder-unification-2026-11-24/README.md)
separate synthetic host measurements from MCU timing and listening claims.

## Checking quantized and switched LPC synthesis

The portable [Schur guard](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxLpcStability.h)
checks the actual signed Q12 polynomial after coefficient rounding and every
linear interpolation step. Stable ordered LSF endpoints alone are insufficient.
The standalone [C++ example](examples/lpx-lpc-stability.cpp) uses the production
header; its [independent Python check](examples/lpx-lpc-stability.py) compares
30,015 synthetic vectors with NumPy roots and resolves near-unit cases with
exact integer Schur recursion. Generated inputs stay under ignored `build/`.

This is portable C++11 on wasm32 (Emscripten6.0.12/Clang24, no imports,
`-ffp-contract=off`) and native C++17, without ISA extensions or handwritten
assembly. Fixed stack arrays avoid allocations. The benefit is correctness;
there is no speed claim. Scalar C++ is always available with SIMD/CUDA builds.

A frozen-polynomial check does not prove stability of changing integer IIRs.
LPX also renders from the original carried state and checks source-relative
energy/clipping in local blocks. Failed seeds retry localized lower-order
analysis through the same ten-LSF syntax, then bounded regularization. Never
splice reset waveforms or globally flatten every spectrum to hide oscillation:
independent partial/envelope/tail controls must also pass. This does not certify
arbitrary audio or establish interrupt-active MCU timing. Reproduction and
quality/cost evidence are in the [common-timbre report](../../Codecs/LPX/research/common-timbre-2026-11-24/README.md).

## Match spectral eligibility to its analysis window

For an RMS floor `r` and an FFT window `w`, use
`sum((x*w)^2) / sum(w^2) > r^2` to decide whether a normalized windowed
spectrum contains significant reference energy. An unwindowed RMS test is
inconsistent with a Hann-windowed comparison: an attack at the window edge
can pass that test while almost disappearing from the compared spectrum.
Normalizing such near-silence produces a false source-shape rejection.

The portable LPX guard retains its64-count floor and existing shape/off-band
thresholds, but applies this consistent weighting. A narrow scalar/SIMD
contract checks edge attacks, significant off-band replacement and polarity;
the source-generated tone-burst regression checks complete whole/streaming
output across all levels/rates and search depths. No assembly, ISA extension
or MCU timing claim is introduced. This is a correctness/quality technique,
not a measured speedup. The portable C++11 wasm32/C++17 native build and
explicit CPU/SIMD/CUDA selection remain unchanged.
