# V5 perceptual-objective pilot, 2026-10-28

The new encoder-only objective is available as an explicit experiment. This
bounded pilot found tiny numerical gains and metric tradeoffs, with no basis
for changing the default automatic gate or claiming an audible improvement.
The decoder source and v5 format remain unchanged.

The six controls are the first six explicitly **tuning** profile records in
the frozen encoder-quality baseline: three complete 64,000-sample recordings,
each in profiles 4 and 6. Each has one actual decoder-reset segment. No
evaluation or additional/independent-cohort recording was scored. The exact
strong baseline stream is retained, and the cap is its complete file length
(100% of B). The 95/90% corpus experiment is separate from this pilot.

Both objectives use identical trajectory settings: frame limit 2, adjacent
window 2, beam 2, spectral finalists 2, excitation finalist 1, excitation
horizon 80, maximum full synthesis evaluations 128, amplitude capacity policy,
and lambda 0. Each fit reached 128 full synthesis evaluations. Excitation
search performed 2,571–6,237 local trials per fit; those are reported separately
and must not be hidden inside the full-synthesis limit. The total is 12 fits.

| Search / returned candidate | Weighted error reduction | PCM error reduction | PWM error reduction | Raw winners passing all four floors |
|---|---:|---:|---:|---:|
| SSE / conservative selected | 0.006148% | 0.015838% | 0.027987% | — |
| Perceptual / conservative selected | 0.012977% | 0.015047% | 0.029476% | — |
| SSE / raw objective winner | 0.022316% | 0.035037% | 0.052635% | 2/6 |
| Perceptual / raw objective winner | 0.062866% | -0.026795% | 0.016281% | 0/6 |

Reductions use summed error energy over the same six controls and frozen
weighting contexts. They are not percentages of perceived quality. Negative
PCM reduction means that aggregate error increased. Full per-record original-
level PCM16/PWM SER, STOI, error energy, peak error and objective values are in
`pilot.json`. The perceptual raw winner has lower weighted error than the SSE
raw winner in all six controls, but every perceptual raw winner fails at least
one existing automatic floor. Raw candidates remain separate for listening.

All conservative selected streams keep the baseline file size. One perceptual
raw stream saves one byte; the other raw sizes are unchanged. Total measured
fit CPU time is 58.469 seconds for SSE and 60.297 seconds for perceptual (+3.13%
in this single paired run). Wall fit totals are recorded separately. Initial
warmup is 0.261 seconds; the complete pilot including independent checks takes
125.783 seconds. These observations do not establish a general speed ratio.

The objective reuses the old weighting kernel without modifying it. A uniform
seed-wide denominator bound prevents unstable floating-point weighting on
otherwise valid clipped v5 LPC; requested gamma2 is 0.6, effective gamma2 is
0.35663–0.42835 across these six controls. Each candidate uses the same frozen
context as its baseline. Independent tests also cover a legal profile-6 v5
fixture whose old denominator has a pole radius above 4, SciPy time-varying
history reconstruction, branch/reset ownership, and continuous weighting over
multiple independently reset decoder streams.

Every seed, conservative selected stream and raw stream was checked over the
full 64,000 samples against both native layouts, the independent clipped
integer model and native PWM. The wrapper independently repeats the unchanged
`no_regression` gate. The 108 source files were checked before and after the
pilot, including exact byte comparison of all nine decoder files with commit
`5c7e0592`. `pilot.json` pins source hashes, search settings, CPU/wall counts,
compiler identity and package versions. Recording paths and recording/stream/
PCM fingerprints, audio and generated firmware remain only in ignored build.

This is a tuning-only finite search, not a holdout result, perceptual optimum,
blind listening result, full-Flash measurement or IRQ timing admission.
Changed excitation parameters can alter execution timing despite unchanged
decoder sources. Full-corpus 100/95/90% and target-player admission remain
separate requirements.

See [objective API and reproduction](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_OBJECTIVE.md)
and [trajectory bounds](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_TRAJECTORY.md).
