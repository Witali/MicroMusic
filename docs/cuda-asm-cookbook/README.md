# CUDA optimization cookbook

## Exact parallel LPX pulse search

The original project kernel in
[LpxCuda.cu](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/cuda/LpxCuda.cu)
evaluates independent excitation candidates for the existing LPX V9 host
encoder. This is CUDA C++, without handwritten PTX or imported kernel code.
It concerns encoding speed, not decoder timing, firmware size or AVR support.

### Target and explicit fallback

The validated device is NVIDIA GeForce RTX 5060 Ti, compute capability 12.0,
with driver 621.14 and CUDA Toolkit 13.3.73. The kernel self-test uses NVIDIA
NVCC, C++17, `-O3 --fmad=false -arch=sm_120`, and MSVC 14.51.36231 with
`/O2 /fp:strict`. Other GPU architectures require a matching explicit build
target and their own validation; no performance portability is claimed.

Compile the GPU translation unit with both NVIDIA's `__CUDACC__` definition
and the separate `LPX_ENCODER_ENABLE_CUDA=1` setting. The normal build defaults
that setting to zero. Even a CUDA-enabled executable defaults to portable CPU
arithmetic; `enc_set_backend(1)` explicitly selects CUDA and
`enc_set_backend(0)` selects the equivalent CPU implementation. Runtime GPU
errors fail the requested encode. The encoder never silently changes backends.

The shared host ABI is ordinary C++ POD: 32-bit signed integers, PCM16 and
double error values. CUDA headers and hardware access stay inside the GPU
translation unit. The scalar encoder and browser WASM need no CUDA SDK.
Use the installed NVIDIA SDK's headers; do not copy vendor definitions into
the project.

### Parallelize choices and retain sequential codec history

One GPU block owns a fixed scale, pitch lag and gain. Its lanes evaluate all
32 P4 or 320 P6 pulse candidates for a 20-sample group. An ordered reduction
selects the smallest `(error, original candidate index)`. One lane replays the
winner into shared LPC history, deemphasis state and the full excitation ring.
The next group starts only after that replay. Eight groups complete a
160-sample block; a second ordered reduction selects the first best parameter
tuple. No history resets occur between encoded blocks.

Lags are at least 18. During a 20-sample trial, only generated excitation
samples zero and one can feed back. A losing lane therefore needs ten LPC
history values, deemphasis state and those two excitation values; it reads
the rest of the preceding ring without copying 256 entries per lane.

Use exact integer prediction, saturation and arithmetic shifts. A block's
loss is at most `160 * 65535^2 < 2^40`, so double represents every accumulated
integer squared error exactly. Preserve the scalar summation order and strict
tie order. Do not enable fast math. The host replays every GPU winner through
portable arithmetic and compares the complete state and loss, then verifies
the final LPX file sample by sample through the common decoder.

Device buffers and a private stream persist between jobs. Transfer one job
and its winning result, rather than returning every losing state. Keep CUDA
initialization outside a warm kernel timing and report cold process latency
separately: short inputs may spend more time initializing the GPU than encoding.

### Validation and measurements

The retained independent
[self-test](../../web-player/tests/helpers/lpx-cuda-selftest.cpp) passed
4,461 jobs containing 24,741 parameter tuples on the device above. It compares
all eight pulses, the tuple index, exact double loss and every final-state
field with a direct exhaustive CPU implementation. Coverage includes both
profiles, zero/clipped signals, equal-error ties, pre-emphasis 0/8192/13926,
short pitch feedback, ring wrap, state extremes, up to 512 choices, ten invalid
jobs and valid-job recovery.

Those direct-kernel timings are validation diagnostics, not a speedup against
the optimized full CPU encoder. Use
[benchmark-lpx-cuda.mjs](../../web-player/scripts/benchmark-lpx-cuda.mjs)
for paired production-encoder checks on identical PCM. It records CPU/CUDA
LPX byte equality, exact decoded length, cold process time and the CLI's
separate initialization/first/warm encoding timings. Per-recording reports,
media fingerprints and source metadata must remain in ignored local storage.

NVIDIA's [compiler documentation](https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/index.html)
defines the explicit architecture and `--fmad=false` options. The
[floating-point guide](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/mathematical-functions.html)
describes operator rounding. NVIDIA's installed headers retain their vendor
licensing; the LPX kernels and arithmetic organization above are project code.
