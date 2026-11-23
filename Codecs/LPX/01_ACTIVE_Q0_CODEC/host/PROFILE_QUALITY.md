# Protected encoder quality search

The expanded adaptive encoder adds a bounded phase after selecting its complete
previous result. It supports P4/P6 at 8, 12 and 16 kHz and the 3/8 kbit/s encoder
presets. A preset is a complete-file ceiling, not padding to a constant rate.
Sparse80 decoding remains supported; the separate offline Sparse80 encoder is
not part of this P4/P6 search.

The phase changes encoder decisions only. It uses existing V9 syntax and the
existing integer synthesis model, with no additional decoder operation or
decoder working memory. Native CPU, explicit CUDA, scalar WASM and SIMD WASM use
the same controller. An optional seed backend failure is reported; it cannot
silently switch the requested backend.

## Fixed proposals

1. Keep the exact previous selected stream, not just a freshly generated seed.
2. Propose LPC bandwidth expansion .94 and .99, retaining the original .97
   default for every ordinary seed call. P4/P6 use the incumbent's pre-emphasis
   and also test its brightness setting. Strict 3k reuses its existing spectral
   allocator and closed-loop excitation with the incumbent as its first floor.
3. Apply pairwise pulse lookahead to the selected protected stream. Up to 24
   frames are chosen by error and distributed coverage. Each pair compares the
   incumbent and immediate/delayed first-pulse finalists, exhaustively fitting
   the legal second pulse from each exact synthesis state. Local work is bounded
   by 246,000 trajectories and four complete-output proposals. Pulse widths,
   spectra, parameters, filters and extras stay fixed in this operator.
4. Propose native-rate magnitude/time pulse fits in at most four high-error
   regions, separated by 768 samples. Exhaustively refit eight legal existing
   pulses per region against three 512/Hann frames, using exact synthesis
   prefixes and a bounded 768-sample horizon. PCM and PWM both contribute.
   Local work is at most 9,632 trials; all/top-two/top-one backoff produces at
   most three unguarded proposals. Only pulse values change, at fixed width.
5. Re-render and verify every unique complete proposal against the C decoder.
   Keep the admissible minimum multi-metric score, breaking equal scores by size.

The exact prior stream stays available throughout. Valid actual-rate STOI,
source-period match counts, collapsed-frame counts and clipping are safety
floors. For both PCM and PWM, total magnitude error, balanced band magnitude
error and balanced temporal magnitude error must not increase. The previous
strict per-band retention gate is retained for research comparisons, but is not
the current selection rule: its first 24-case public pilot retained every
incumbent at increased encoder cost.

The current score compares every loss to the same complete incumbent. Magnitude
spectral error and temporal magnitude-change error each have weight two; voice,
noise and waveform SSE each have weight one, as do STOI loss, period error and
coarse spectral-shape error when defined. Average across both PCM and PWM and
divide by the included weights. A zero incumbent error remains an exact floor.
Waveform SSE contributes to the score and is reported, but need not be identical
or lower: different noise samples can have the correct spectrum and timing.
Individual metric tradeoffs must be reported rather than described as universal
metric improvements. See [full-band-quality.md](full-band-quality.md).

The 8 kHz voice/noise analysis is auxiliary at higher rates. Actual-rate STOI
uses pinned rational FIRs. Full-rate waveform errors and native 1 kHz spectral
bands cover DC through Nyquist: 4, 6 and 8 kHz at the respective sample rates.
Resampling an 8 kHz original cannot validate preservation of genuine source
content above 4 kHz; native wideband sources and synthetic controls are separate
requirements for that claim. Objective gains alone do not establish an audible
improvement.

## Budgets and reproducibility

Ordinary adaptive P4/P6 retain their existing complete v5 control budget before
lossless V9 packing. Strict 3k uses actual complete V9 bytes. The 8k preset uses
the existing conservative conversion between these accounting conventions and
checks its final V9 file. This phase never expands the supplied cap. Any optional
file metadata must be reserved by the outer controller before this search.

Compile with `LPX_ENCODER_QUALITY_SEARCH=0` to select the prior expanded encoder
without this phase. The classic `enc_adaptive`/reference search remains available
independently. These switches do not choose CPU arithmetic or enable assembly.
`LPX_ENCODER_SPECTRAL_PULSES=0` selects the preceding V2 proposal set with the
same objective, without native spectral pulse fitting.
All seed calls explicitly restore their requested bandwidth, so a prior .99
proposal cannot affect a later default .97 seed or stepped `enc_begin` call.

`ProfileQualityReport` records unique proposal counts, selected improvements,
bandwidth attempts, lookahead work and spectral pulse work. The native CLI includes these counters in
its JSON report. Encoder runtime and actual final bytes must be reported with
quality measurements; no real-time encoding guarantee is implied.

The prospective corpus protocol and anonymous results live under
`Codecs/LPX/research/v9-quality-all-2026-11-23/`. Private media and provenance stay
in ignored build directories. Narrow tests cover exact prior 8 kHz evaluation,
true-rate numerical oracles, tails, continuous Long output, strict budgets,
quiet/silent/high-frequency controls and seed-state reset.

## Appended joint refinement

`refineJointQuality()` starts from the complete previous V3 winner. It freezes
that winner as its own floor and uses the same complete-output admission and
metric equations. Its relative report scores belong to this separate phase;
they must not be multiplied by earlier phase scores.

P4/P6 proposals change one legal quantized LSF coordinate across a whole existing
run of identical spectra. Internal repeat coding is preserved. Four runs, at
most twenty coordinate shapes per run, two shortlisted shapes, a 1280-sample
local horizon and a 160-sample pulse neighborhood bound the local work. Exact
prefix/interpolation synthesis supplies proposals; local spectral/time scores
are only ranking approximations. Up to eight whole-output proposals pass to
the common final gate. Individually safe score-improving edits from different
runs can also be combined: one best edit per run, then all/top-two bundles.
This adds at most two complete checks without rerunning the local shape search.
Every single and the original complete winner remain available. This does not
add decoder operations or format fields.

Strict 3 kbit/s also proposes the existing header fits before and after those
edits. A development ablation found no selected change in five paired jobs
from regenerating three additional full seed searches, at roughly twice the
API time. That extra search and its visitor API were removed from production.
No new codebook or side information is introduced.

The supplied complete cap is unchanged. An improved candidate can use spare
bytes within that cap even when its actual file is slightly larger than the
incumbent. Report both actual sizes, all metric tradeoffs and encoder runtime.
This is bounded search, not a proof of a global optimum or an audible gain.

`LPX_ENCODER_JOINT_REFINEMENT=0` restores the preceding V3 selection.
`LPX_ENCODER_LPC_RUNS=0` omits the run operator for controlled ablation. These
host switches do not affect MCU arithmetic selection. Native CPU/CUDA and
scalar/SIMD WASM share the same phase and optional input normalization.

The new prospective study is documented in
[`lowrate-quality-next-2026-11-23`](../../research/lowrate-quality-next-2026-11-23/PROTOCOL.md).
