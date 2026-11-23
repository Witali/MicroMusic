# Exact native LPX CUDA encoder measurements

Measured on 23 November 2026 on an NVIDIA GeForce RTX 5060 Ti (compute 12.0,
driver 621.14). Shared host code uses Clang 24 with the Microsoft ABI and strict
floating-point flags; the CUDA kernel uses NVCC 13.3.73, `--fmad=false` and
`sm_120`. [native-build.json](native-build.json) retains source hashes, actual
toolchain versions, vendor-header hashes, flags and final executable hashes.

CUDA accelerates the existing closed-loop seed pulse search. The native command
also retains explicitly selectable CPU arithmetic. Both paths use the same
adaptive controller, quality gates, integer synthesis and V9 packing. GPU
winners are replayed and checked through portable arithmetic before the final
file is verified by the shared C decoder. CUDA errors stop the requested encode.

## Full input and quality checks

The fast-mode corpus contains 227 complete prepared inputs: 181 archived cases
and 46 audiobook cases covering all 21 local audiobook files. There are 95
speech inputs and 132 other controls, 23,258,635 input samples in total at
8 kHz, and 12 continuous Long inputs. The largest is 4,998,606 samples
(624.826 seconds), a complete source recording. The other audiobook cases are
declared test excerpts, not a claim that all books were encoded in full.

All **454 CPU/CUDA files** (P4 and P6 for every input) match byte for byte,
including full continuous Long output. The final expanded adaptive comparison
separately covers four inputs: Russian, English, an audiobook excerpt and a
16-second continuous Long excerpt. All eight profile results also match.

The independent GPU-kernel harness additionally passed 4,461 jobs / 24,741
parameter tuples, with exact pulse choices, loss, tie order and full state,
plus ten invalid-job checks. Its retained
[receipt](kernel-validation.json) binds the original kernel and reference test.
It is a correctness check, not the optimized full CPU comparison below.

## Observed encoding times

Times below include search, allocation, packing and complete native validation.
They exclude GPU initialization, process startup and source conversion.

| Mode | Profile cases | CPU total | CUDA total | CPU / CUDA |
| --- | ---: | ---: | ---: | ---: |
| Fast P4 | 227 | 56.744 s | 18.731 s | 3.03× |
| Fast P6 | 227 | 399.215 s | 21.191 s | 18.84× |
| Expanded adaptive P4 | 4 | 67.574 s | 61.714 s | 1.09× |
| Expanded adaptive P6 | 4 | 77.071 s | 66.223 s | 1.16× |

The full adaptive pipeline still performs its spectral/periodicity/STOI gates,
header search and joint refinements on the CPU. Its speedups must not be
described using the fast-mode ratios. One adaptive P4 pair was slightly slower
with CUDA; these bounded measurements do not establish a gain on every input.

Three eight-second fast-mode recordings were also encoded three times per
process, checking repeat determinism. Median warm speedups were 3.48× for P4
and 20.32× for P6 (P6 range 20.24–22.13×). GPU initialization in that run took
about 76–111 ms. Across the whole fast corpus, median cold process ratios were
0.62× for P4 and 3.22× for P6: startup can make short or silent P4 inputs slower.
CPU remains the default backend. Background development work was not isolated;
these observations concern this workload, build and GPU.

[measurements.json](measurements.json) contains aggregate numerical results.
Recordings, book names, speaker identities, per-recording hashes, source paths
and private manifests are excluded. Archived metadata identifies eight main
speakers and does not substantiate hundreds of independent voices. No subjective
listening, other-GPU performance, AVR timing or buffer-underrun claim is made.

## Reproduction

Build the production CPU/CUDA commands as described in
[the native encoder README](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/host/README.md).
Prepare the local private corpus without adding audio to Git, then run:

```text
node web-player/scripts/benchmark-lpx-cuda.mjs --encoder build/lpx-native/lpx-encode-cuda.exe --manifest <private-corpus-manifest> --repeat 1 --output build/cuda-corpus-fast.private.json
node web-player/scripts/benchmark-lpx-cuda.mjs --encoder build/lpx-native/lpx-encode-cuda.exe --manifest <private-corpus-manifest> --quality adaptive --cases <anonymous-case-indices> --repeat 1 --output build/cuda-corpus-adaptive.private.json
node web-player/scripts/summarize-lpx-cuda.mjs --input build/cuda-corpus-fast.private.json --adaptive build/cuda-corpus-adaptive.private.json --output build/cuda-summary.json
```

The driver checks prepared PCM hashes locally, compares complete CPU/CUDA files,
decodes the result and records cold wall time separately from native timings.
`--repeat 3` keeps one CUDA context alive for repeated timing. Private reports
must remain in ignored build storage; the driver rejects output symlinks and
junctions. Export only the aggregate summary for publication.
