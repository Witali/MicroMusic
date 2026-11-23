# Optional whole-file perceived-loudness normalization

The Web UI now defaults to one constant coefficient stored in the completed
LPX file. Its switch enables/disables this feature; target mono LUFS and maximum
boost are configurable. Measurement uses the final decoded recording. The
payload is unchanged for P4/P6; 3/8 presets first reserve two metadata bytes.
The decoder applies the coefficient at final output on Web, PC and MCU.
See [the wire specification](../LPX9_GAIN_FORMAT.md). There is no intra-file AGC
and no reaction-time parameter for a constant coefficient.

The default settings are -18 LUFS and maximum +12 dB; the decoded sample-peak
ceiling is -1 dBFS. The result reports the actual coefficient, resulting LUFS
and any limiting constraint. Disabling normalization retains the original bytes.
Short/below-gate audio uses unity. Source stereo is downmixed before encoding.

`normalizeFileGain` and `enc_adaptive_file_gain` / `enc_bitrate_file_gain` implement
the current policy. It uses the same independently checked meter described below,
retains strict complete-stream verification, and changes no synthesis history.

## Retained pre-encoding reference API

The older `enc_adaptive_loudness` and `enc_bitrate_loudness` ABIs below remain
selectable for compatibility/regression. The page uses the file-gain policy.

The reference API preserves input level by default. Selecting **loudness**
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
The `enc_bitrate_loudness` ABI provides the same preprocessing for 3/8 kbit/s
presets at 8 kHz. Their exact complete-file caps remain unchanged; normalization
happens before candidate selection and does not scale a finished LPX stream.

The reference fixture uses independently built libebur128 v1.2.6 on 42
deterministic PCM16 cases at 8/12/16 kHz: tones at several frequencies, quiet
and loud material, noise, pauses, transients, DC, silence, below-gate signals,
400-ms boundaries and incomplete tails. Tests also check exact native/scalar/
SIMD PCM, target tolerance when reachable, peak constraints, complete duration,
polarity, pause preservation, opt-in worker propagation and unchanged default
LPX bytes against the previously shipped module. See
`web-player/tests/lpx-loudness.test.mjs` and its reference fixture. These checks
are numerical validation, not meter certification or a listening guarantee.
