# Bounded v5 trajectory pilot

The multi-frame algorithm is implemented and exact-output checks pass. In this
small tuning pilot it **does not beat the expanded legacy optimizer under the
existing automatic quality floors**. Local screening makes more adjacent-frame
search practical at comparable CPU time, but its raw SSE improvements remain
tradeoff alternatives. No listening or general corpus-quality gain is claimed.

Scope: one tuning recording encoded in profiles 4 and 6, complete frozen
64,000-sample reference at original level, and 100% of its already achieved
stream size. Caps are 3,547 / 5,181 bytes, including the entire v5 file. No
evaluation, additional or independent recordings were used for these choices.
This is two profile controls on one recording, not two independent voices.
The root study separately owns full-corpus 100/95/90 admission.

## Controls and measured time

All methods start from the identical strong seed per profile. Existing
`refine_speech_lpc` remains the conservative control. Its default settings are
32 anchors / 2 spectral finalists / 640 lookahead / 80 excitation horizon /
one pass. Expanded legacy uses 64 / 4 / 1280 / 160 / two passes.

Beam settings are two anchor windows, two adjacent frames per window, width 2,
two spectral finalists, one excitation finalist and an 80-sample refit horizon.
Every complete candidate is ranked on the whole original-length waveform and
actual serialized bytes. The initial/full controls screen scalar LSF neighbors
on the whole suffix; local mode uses exact 640-sample contextual screening
before full ranking. The latter is a proposal heuristic, not a replacement for
whole-reference acceptance.

| Method | Profile 4 CPU, s | Profile 6 CPU, s | Selected PCM SSE, profile 4 | Selected PCM SSE, profile 6 |
| --- | ---: | ---: | ---: | ---: |
| Seed | — | — | 45,184,014,310 | 25,280,506,238 |
| Legacy default | 0.813 | 2.344 | 45,004,120,838 | 25,193,388,230 |
| Legacy expanded | 20.797 | 11.563 | 43,894,102,578 | 24,094,467,014 |
| Initial full-screen beam, 128 evaluations | 14.016 | 6.531 | Seed retained | Seed retained |
| Optimized full-screen beam, 128 | 10.875 | 4.609 | Seed retained | Seed retained |
| Local-screen beam, 128 | 11.531 | 6.484 | Seed retained | Seed retained |
| Optimized full-screen beam, 160 | 13.688 | 5.172 | Seed retained | Seed retained |

Warm integer kernels, the same existing CPython 3.12 / NumPy / Numba runtime,
one numerical thread, process CPU and wall time were recorded. These are one
trial per method/profile on this host; no portable timing guarantee follows.
Native validation performed inside each optimizer is included in that call's
CPU time. The final additional cross-backend audit is separate.

The 160-evaluation full control was chosen from timing, without selecting by
quality, to compare CPU with local 128: **18.859 versus 18.016 seconds total**
(local uses 4.47% less). Different explicit bounds are retained in every row.
No claim is based solely on equal evaluation counts, because local probes,
refits, complete suffix evaluations and final metric calculations cost
different amounts.

## Packing and adjacent-window evidence

Removing redundant serialization preserves both initial full-mode selected and
raw stream bytes exactly. Actual serializer calls fall from 270 to 184 on
profile 4, and 266 to 142 on profile 6; observed CPU falls by 22–29%. Some
branches still need serialization before and after genuine capacity changes.
The proof uses exact full-mode byte comparison, not updated expected audio.

At the 128 bound, optimized full mode completes one two-frame window, then
stops before completing a frame of the second. Local mode completes **both**
windows on profile 4 (125 actual complete evaluations); on profile 6 it
completes one window plus the first frame of the interrupted second (128).
The matched full-160 control completes one window plus one frame of the second
on each profile. New reports explicitly record `planned_frames`, completed
`frames`, `complete` / `evaluation_limit` and the interrupted frame. Initial
reports contained only completed checkpoints, so their missing partial work is
not presented as completed adjacent-frame search.

| Raw candidate PCM SSE | Profile 4 | Profile 6 |
| --- | ---: | ---: |
| Full 128 | 45,179,355,594 | 25,254,211,310 |
| Full 160 | 45,179,355,594 | 25,216,249,694 |
| Local 128 | 45,177,448,078 | 25,214,397,530 |

These small raw differences fail at least one existing PCM/PWM SSE/STOI floor
in the selected comparisons. They do not establish audible benefit. The raw
and feasible-frontier streams remain private alternatives; automatic selected
results retain the seed. Error-energy percentages would not be percentages of
perceived sound quality.

All **15 unique retained streams** from these measurements pass complete
PCM16 **and PWM** comparison on native common and compact-only decoders and the
independent model. The decoder source and v5 syntax are unchanged. This
host-only pilot establishes neither physical-board/analog behavior nor an AVR
IRQ admission for newly selected corpus assets.

## Reproduction and retained evidence

[Anonymous rows](rows.json) contain exact settings, timing, actual serialization
counts, separate local/full/refit counters, whole-reference metrics and window
states. [Summary and public code fingerprints](summary.json) identify the
source epochs. Counts named `full_metric_evaluations` in the old optimizer
mean full metric acceptance checks; they are not the same work unit as the
new `full_synthesis_evaluations`.

The [trajectory API and CLI](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_TRAJECTORY.md)
retain explicit full/local modes, per-bit rate units, capacity hooks, and an
unfiltered feasible frontier for whole-reset-chain assembly. Its 15 regression
groups cover delayed non-improving edits, independent exact states, branch
ownership, lower-cap/no-fit behavior, local-screen parity, actual packing
counts and interrupted windows. Strong seeds, ordered private manifests,
recording paths, media/PCM/PWM/stream hashes and complete alternatives remain
in ignored build storage. No private-media fingerprints are published here.


[Predeclared nonzero-lambda sweep](LAMBDA_SWEEP.md) records actual serialized size/quality points, conservative and raw alternatives, complete native/model/PWM audit and finite-search outcomes at alpha 0 / 0.1 / 1.
