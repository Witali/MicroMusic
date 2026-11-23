# Frame-by-frame STOI working buffers

The original metric simultaneously retained full resampled reference/candidate
signals, silence-removed overlap-add signals, and both STFT band sequences.
The replacement retains only frame energies for the unchanged global silence
mask. Resampling uses a256-sample frame cache, overlap-add uses128-sample halves,
and correlation uses30 band frames. FIR summation, exclusive framing, mask
threshold, window functions and correlation accumulation order remain intact.
This is a storage refactoring, not a new quality objective.

A GCC `-O2 -ffp-contract=off` differential check against the original source at
`69e915d4ad5023d6a1521c8ba3b31b06c76d7496` compared48 synthetic combinations:
eight lengths1,3277,3278,4096,16000,65537,192001,1048576 and six classes (silence,
tone, deterministic noise, sparse near-gate noise, pauses and a loud prefix).
All finite double results were bit-identical; NaN cases agreed.

A standalone scalar WASM allocation probe used the production allocator and
seed workspace,1100000 generated tone samples, identical reference/candidate,
and a64 MiB linear-memory limit. The original trapped with65208320 allocated
bytes. The replacement completed with29229056 bytes and STOI
0.9999999999999727. Compiler: Emscripten6.0.12 LLVM24, `-O3`, no exceptions,
`-ffp-contract=off`, production adaptive flags, with only the memory ceiling
changed for the probe. These are synthetic tests, with no private audio.

The energy summary and caller-owned PCM still scale with duration. This change
alone does not make the entire adaptive pipeline bounded-memory, establish a
particular maximum recording length, or prove audible quality gains. It removes
the full-size floating signals from this metric while preserving its results.
