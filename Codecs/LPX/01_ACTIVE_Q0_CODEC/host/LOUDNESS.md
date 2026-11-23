# Optional perceived-loudness normalization

The Web/PC encoder preserves input level by default. Selecting **loudness**
normalizes mono PCM16 before adaptive encoding toward **-18 LUFS**, with a
**-1 dBFS sample-peak ceiling**. The target is a project choice, not an ITU or
EBU programme-delivery recommendation. One constant gain applies to the entire
recording; no compressor, limiter, gating of output samples, chunking, history
reset, or time-varying gain is introduced. Lossy encoding can change loudness;
the UI reports measured decoded LPX loudness separately.

The shared `LpxLoudness.cpp` implements mono integrated measurement following
[ITU-R BS.1770-5, Annex 1](https://www.itu.int/rec/R-REC-BS.1770-5-202311-I/en):
K weighting, complete 400-ms blocks at 100-ms steps, the -70 LUFS absolute
gate and the -10 LU relative gate. Stereo is downmixed by the existing browser
preparation before measurement. Mono has one channel of weight 1; this is not
dual-mono/stereo loudness. Filter state continues through all pauses.

The sample-rate-dependent K-filter design is adapted from **libebur128 v1.2.6**
[`ebur128_init_filter`](https://github.com/jiixyj/libebur128/blob/v1.2.6/ebur128/ebur128.c).
Its MIT [license](LICENSE-libebur128.txt) is retained unchanged and shipped with
the website. Project-specific block accumulation, gain application, reports and
encoder integration are separate original code. Only the filter design is
adapted; libebur128 is used independently as a test oracle, not shipped as a
runtime dependency. The pinned upstream source URL is
`https://raw.githubusercontent.com/jiixyj/libebur128/v1.2.6/ebur128/ebur128.c`.

Recordings shorter than 400 ms and signals with no block above the absolute
gate keep their original PCM and report that normalization was skipped. No
zero padding or peak-normalization substitute is used. A high crest factor
can make the LUFS target unreachable; in that case the peak ceiling wins and
the UI reports the limitation. The ceiling applies to input samples before
lossy coding; it is not a true-peak or decoded-output ceiling. Previously
clipped source audio cannot be repaired by a constant gain.

The normalizer is portable C++11, with no assembly, Python, JS audio DSP or
architecture-specific backend. Native PC, scalar WASM and SIMD WASM compile
the same source. The existing adaptive ABIs remain unchanged; the new
`enc_adaptive_loudness` ABI opts in. Quality selection compares candidates
against the normalized reference. Report getters expose source, prepared and
decoded LUFS, applied dB gain, skip status and the peak constraint.

The reference fixture uses independently built libebur128 v1.2.6 on 42
deterministic PCM16 cases at 8/12/16 kHz: tones at several frequencies, quiet
and loud material, noise, pauses, transients, DC, silence, below-gate signals,
400-ms boundaries and incomplete tails. Tests also check exact native/scalar/
SIMD PCM, target tolerance when reachable, peak constraints, complete duration,
polarity, pause preservation, opt-in worker propagation and unchanged default
LPX bytes against the previously shipped module. See
`web-player/tests/lpx-loudness.test.mjs` and its reference fixture. These checks
are numerical validation, not meter certification or a listening guarantee.
