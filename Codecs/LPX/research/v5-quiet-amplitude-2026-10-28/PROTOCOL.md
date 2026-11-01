# Frozen 16-case quiet-amplitude diagnostic

This protocol is fixed before any run. It is a bounded synthetic stress test,
not a new encoder setting, original-corpus result, speaker/voice-gender test or
firmware admission. Do not change source, thresholds, weights or the case set
in response to observed outcomes.

## Exactly 16 cases

- Sample rate 8,000 Hz; original length 8,000 samples, with no trimming,
  playback normalization, resampling, delay alignment or fitted gain.
- Known fundamental 200 Hz. For integer sample index `n=0..7999`, construct
  `s(n) = .7*sin(2*pi*200*n/8000) + .2*sin(2*pi*400*n/8000)
  + .1*sin(2*pi*600*n/8000)` in float64.
- Independently scale this analytic source by each of `1, 4, 32, 1024`, then
  apply exactly one `numpy.rint` and cast to PCM16. These names are nominal
  scales, not guaranteed final peaks. Report actual integer peak/RMS/levels,
  and leave a quantized-away or unassessed source explicit.
- Cross each scale with profiles 4 and 6, and `preQ14` 0 and 13926:
  `4 * 2 * 2 = 16` cases, deterministic increasing scale/profile/pre order.
- Use fresh `speech_v4.encode` with the chosen profile/pre and its unchanged
  default bandwidth 0.97. Repack each result through `speech_compact.repack`.
  No refine/enhance/objective search, extra pulses, threshold tuning, manual
  pulse edit or seed selection is added.

## Checks and reports

Require complete native-common V4 PCM/PWM, native-common V5 PCM/PWM and native
v5-only PCM/PWM to equal their unchanged integer models at all 8,000 samples.
V4-to-V5 repack must preserve every decoded sample. Record actual complete
V4/V5 bytes, including headers, tails and padding. Any encode/fit/validation
failure stays an explicit row, with no automatic replacement or case deletion.
No byte or full-Flash fit claim follows from this host test.

Use the frozen `voice_character.PitchSettings()` from component `065716f5`
and its source-supported candidate-period windows. Report source candidate
count, paired/cents/missing/output-period errors, fixed-source-period residual,
spectral shape, original-level descriptors and collapsed windows separately
for native PCM16 and fixed PWM. Missing reference periodicity is unassessed;
missing decoded periodicity is a failure relative to observed source periods.
These are diagnostics, not validated true-F0 or perceived timbre scores.

Record complete original-level waveform SSE numerically with `speech=False`;
STOI does not assess this analytic harmonic tone. Also report source/output
nonzero counts, integer level counts, decoded DC/RMS, non-neutral PWM count,
stored scale-step range, gain/lag summaries and innovation amplitude counts.
Profile 4 has compulsory +/-8 innovations, while profile 6 also differs in
other coding details. Any measured difference is not an isolated causal proof
that the innovation amplitude alone caused it.

Bind runner, diagnostic, encoder/model/native-source and runtime versions
before/after the run. Retain all input/output streams, WAVs, library identities,
hashes and detailed receipts only in owned ignored `build/` storage. Public
evidence may contain the analytic formula, source-code provenance and anonymous
numeric outcomes. Do not add MIDI. No AVR build, board/analog measurement,
new production default or full-corpus expansion belongs to this experiment.
