# Fixed-size voice-objective trajectory probe

This diagnostic is declared before its outcomes. It is separate from the frozen
V2 98/14/6 corpus experiment and does not extend or alter its candidate pools,
selection rules, byte ceilings, implementation or worker receipts.

Use the existing four-second gain-64 target and exactly two already measured
profile-4 seeds: the accepted V1 1702-byte stream and unified-search A at 1710
bytes. Each seed is its own quality anchor and complete-byte cap. No initial
encoding, gain fit, trimming, resampling, new decoder code or new format is used.
These are two probes of one tuning source, not independent held-out cases.

Call the existing `refine_speech_trajectory.refine` once per seed, with eight
anchors, two-frame windows, beam width 3, two spectral and two excitation
finalists, 160-sample excitation horizon and at most 128 full render evaluations.
Use local screening with a 640-sample horizon, capacity policy `none`, zero
allocation evaluations and zero rate lambda. Freeze these settings for both
seeds; do not retry with another budget or grid after seeing a result.

The full-output objective is the frozen V2 mean of VoiceObjective plus
NoiseObjective across native PCM16 and fixed PWM. Reference periods and natural
source noise are frozen before refinement. Existing trajectory conservative
PCM/PWM SSE/STOI acceptance stays active. Independently remeasure the input,
selected, raw and retained frontier endpoints, verify both native layouts/model,
and additionally apply V2 within-100-cent coverage, no added clipping and joint
score floors against each seed. Missing output pitch remains failure/unknown.

Retain the seed independently of any search/pruning. A helper-selected or raw
stream is only a measured alternative until all outer gates pass. Keep actual
serialized size, full rendering/objective/local counters, wall and process CPU
time, decoder checks and source provenance. The render limit does not bound
all local screening work or elapsed time. No result is a global optimum or a
same-CPU comparison with the earlier four-call controller.

Persist attempts before work and final markers only after source/input/native
checks. Preserve failed attempts; no refit or automatic retry is allowed. All
media, streams, input/output fingerprints and detailed paths stay in ignored
build output. Public evidence contains numerical results and source-code
provenance. A potential numerical gain requires later unchanged-size listening,
held-out/corpus evaluation and actual full-player admission before adoption.
Negative or marginal results do not justify another production search branch.
