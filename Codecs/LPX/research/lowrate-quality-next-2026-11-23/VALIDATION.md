# Validation of the frozen joint-quality implementation

Algorithm sources are frozen at `403de620`; the later cache and cookbook
commits do not alter them. Corpus quality results and their limitations are
separate in [README.md](README.md).

## Search and continuation contracts

- Native complete joint selection: 16 checks, including seven improvements,
  original caps, exact C decoding, disabled-brightness preservation and native
  octave floors.
- LPC proposals: 144 cases, including 102 exact prefix/coefficient slices and
  258 legal proposals. Composition covers 12 profile/rate/budget matrices,
  deterministic ties, caps and rejected malformed/context-mismatched inputs.
- Continuation: 60 carried-state cases and 12 composition matrices; joined
  prefixes, candidate windows and later suffixes match the C reference.
- Default-zero continuation context: 48 differential cases preserve the
  preceding implementation's ordered proposals, counters and bundles.
- Pitch floor: 131 contracts in native C++, scalar WASM and SIMD WASM. A
  separate NumPy oracle checks 3,465 actual-rate observations with identical
  masks; maximum period difference is 2.84e-14 samples. The former 8-kHz
  estimator and 18 existing metric doubles retain exact differential results.

These are bounded correctness cases, not arbitrary-input or perceptual proofs.

## Production backends and decoder

The final targeted native/streaming Node run passes 19 tests with no failures
or skips. It covers full-mode search, input normalization, explicit backends,
continuous Long output, cross-window history, allocation-failure fallback and
native CLI output/file handling. Native streaming helper subcomparisons are
not enabled in that run; the streaming comparisons use scalar and SIMD WASM.

Two changed public outputs are re-encoded with scalar and SIMD WASM: all four
complete files match the frozen GCC driver byte for byte. The generic P6 job
also matches the Windows CPU and CUDA CLI. Strict-budget jobs use the preset
API rather than a different generic CLI search.

Two changed new-primary outputs, strict 3 kbit/s at 8 kHz and P4 at 16 kHz,
repeat the same comparison: four scalar/SIMD encodes match the frozen GCC
files, and the P4 file also matches Windows CPU/CUDA. Combined coverage is
four changed files, eight WASM encodes and two CPU/two CUDA encodes; this is
representative cross-backend equality, not a re-encode of the whole corpus.

The final WASM decoder independently checks all 312 baseline/selected files
from the public, new-primary and known-regression sets: 11,052,658 decoded
samples match native C PCM and the fixed PWM mapping exactly. Receipts bind
the complete files, PCM, PWM, sample counts and rates; no source/output gain
fitting or alignment is introduced.

The nine selected AVR image measurements are documented in
[firmware-results.md](firmware-results.md), including which six exact-bound
measurements were reused. They cover active interrupts and EOF draining on
fixed public inputs, not physical boards or arbitrary streams. The shared
decoder and MCU player sources are unchanged by this encoder-only refinement.

Private media, paths, detailed receipts, frame observations and raw logs remain
in ignored build directories. No private audio artifact is part of the study
export.
