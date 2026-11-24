# WebGPU optimization cookbook

## Archived exact LPX search experiment

Status: the implementation is retained on `codex/lpx-webgpu-batch` at commit
`25b401cd3aac78002ea81797788dd48abe653931`; the original single-block experiment
is on `codex/lpx-webgpu` at `a0939f12`. Main retains this technique and its
[measurement report](../../research/web-encoder-webgpu-batch-2026-11-24/README.md).
The production encoder continues to select WASM SIMD / portable WASM.

This is original WGSL compute code, not handwritten assembly. The measured
target was Windows x64, Chrome 158, NVIDIA Blackwell, Emscripten 6.0.12 / Clang
24, C++11, `-O3 -ffp-contract=off -msimd128`. It requires hardware WebGPU and
WebAssembly JSPI. Host encoding measurements establish no MCU timing profile.

### Reusable techniques and correctness constraints

- Parallelize the 32 P4 / 320 P6 excitation candidates within one 20-sample
  group. Select by exact `(loss, original ordinal)` and replay the winner before
  starting the next group. Retain sequential LPC, excitation and deemphasis
  history; arbitrary blocks cannot be encoded independently.
- Keep bounded signed 32-bit prediction and use two `u32` words for squared
  error. A PCM difference square fits `u32`, but 160 samples can require 40
  bits. The sum remains exactly representable when returned to WASM double.

  ```wgsl
  let lo = a.x + b.x;
  let sum = vec2<u32>(lo, a.y + b.y + select(0u, 1u, lo < a.x));
  ```

- Separate source-derived pitch/gain/scale planning from synthesis history.
  Prepare up to 128 jobs, execute ordered search/select/copy passes, and copy
  each winning state directly into the next GPU job. One upload/readback serves
  the whole batch; upload only the first state and the live parameter payloads.
- Validate the incoming state and exact job before consuming a cached winner.
  Independently replay every winner in portable C++ and check its complete
  state/loss. Preserve the CPU's state-dependent silence shortcut by ending a
  batch before a future eligible zero-residual block.
- Keep an explicitly selectable batch-size-1 mode and portable CPU arithmetic,
  even in the GPU-enabled WASM module. JSPI suspends the shared C++ stack rather
  than introducing a separate codec implementation. The bridge reuses the
  historical CUDA POD ABI but links no CUDA SDK, kernel or runtime.

### Measured benefit and decision

Batching reduced five-minute-stream round trips from one per block to 127.1
blocks per round trip. Short fast GPU encodes improved 3.82x / 4.31x against the
same module with batch size 1. The gain over SIMD was much smaller and varied
by mode; some short workloads remained slower. Startup was about 393 ms for
GPU versus 10 ms for SIMD, and batches add bounded host/device storage.

The complete LPX stayed byte-exact against CPU/SIMD, including five-minute
inputs, all tested batch sizes and raw-seed silence transitions. The branch's
regression recorded 201 passes, 34 optional skips and no failures. These are
measured synthetic workloads on one browser/device, not a universal speedup.
The experiment is retained for reuse rather than enabled in main.

Reusable source at the retained commit: `web-player/lpx/webgpu-search.wgsl`,
`web-player/lpx/webgpu-search.js` and `web-player/lpx/native/webgpu-search.cpp`.
The branch's cookbook contains the full ABI and memory accounting. Primary API
references are [WebGPU](https://www.w3.org/TR/webgpu/),
[WGSL](https://www.w3.org/TR/WGSL/) and
[WebAssembly JSPI](https://v8.dev/blog/jspi-newapi). The kernel organization
derives from original project C++/CUDA code; no external shader code was copied.
