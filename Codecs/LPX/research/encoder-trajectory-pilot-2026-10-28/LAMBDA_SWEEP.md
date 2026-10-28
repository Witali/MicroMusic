# Bounded nonzero price sweep

The predeclared price sweep **does not reduce the selected or best raw file
size on these controls**. It does not improve the union size/SSE frontier over
alpha 0. The parameter being nonzero is not evidence of compression.

This reuses the same single tuning recording in profiles 4/6, complete frozen
64,000-sample reference at original level, strongest fixed seed and actual
100% achieved-size cap. Decoder and encoder source stay unchanged at
`f003b43c`. No evaluation/additional recordings are used and no source changes
are made during the sweep.

Before inspecting any outcome, define alpha in `{0, 0.1, 1}` and
`lambda = alpha * baseline_PCM_SSE / (8 * baseline_complete_bytes)`.
`D + lambda * R` uses actual complete serialized bits, including the 22-byte
header, extras markers and byte padding. All six runs retain local screening,
two anchor windows, two adjacent frames, beam width 2, two spectral finalists,
one excitation finalist, horizon 80 and a 128 complete-evaluation bound.
The capacity control remains the same amplitude policy as the prior pilot;
exact marginal/swap allocation is a separate comparison.

| Profile | Alpha | Lambda per bit | Encoder CPU, s | Selected bytes | Best raw bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 | 0 | 0 | 11.688 | 3,547 | 3,547 |
| 4 | 0.1 | 159,233.205 | 12.219 | 3,547 | 3,547 |
| 4 | 1 | 1,592,332.052 | 11.297 | 3,547 | 3,547 |
| 6 | 0 | 0 | 6.047 | 5,181 | 5,181 |
| 6 | 0.1 | 60,993.308 | 6.719 | 5,181 | 5,181 |
| 6 | 1 | 609,933.079 | 6.922 | 5,181 | 5,181 |

Profile 4 completes both two-frame windows with 125 complete evaluations and
108 local probes. Profile 6 uses 128 complete evaluations and 118 local
probes, completes one window and one frame of the next, and explicitly reports
that interrupted window. Prices do not remove the declared finite bound.
There is one timing trial per cell, so these timings establish neither a
lambda speed trend nor portable performance.

The retained frontier includes one-byte-smaller alternatives (3,546 / 5,180 B)
already found at alpha 0. They fail the existing automatic PCM/PWM SSE/STOI
floors. Alpha 1 finds a **worse** profile-4 point at the same smaller size,
dominated by the alpha-0 point. All price runs keep the conservative selected
seed; their best raw winner remains the same size. This demonstrates why a
finite beam's price response need not be monotonic or globally optimal.

At alpha 0, the smaller profile-4 point has PCM SSE 45,216,633,874 versus the
seed's 45,184,014,310; PCM/PWM STOI also decline. The smaller profile-6 point
has PCM SSE 25,237,072,746 versus 25,280,506,238, but its PCM/PWM STOI decline.
The latter is an explicit metric tradeoff, not an automatic quality gain.
The complete numeric frontier and all PCM/PWM metrics are retained in
[anonymous sweep rows](lambda-sweep.json). An SSE/rate frontier does not
replace the STOI floors or whole-reset-chain evaluation.

All **seven unique outputs** across selected, raw and frontier alternatives
pass complete PCM16 and PWM comparison on both native common and compact-only
decoders and the independent model. Alpha-0 selected/raw bytes reproduce the
previous local-screen pilot exactly. No physical-board, listening,
optimal-lambda or general corpus-size claim is made. A larger price might
change outcomes, but it was not part of this predeclared experiment.

Only anonymous numeric evidence and public source fingerprints are committed.
Actual streams, reference paths, original IDs and media/PCM/PWM/stream hashes
remain in ignored build storage.
