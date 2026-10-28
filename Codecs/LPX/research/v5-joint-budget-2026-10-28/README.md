# Joint LPC search and automatic complete-Flash budgets

Offline v5 search now changes legal quantized LSF/LPC and nearby excitation.
The automatic selector compares real linked firmware images, including complete
reset chains. **The C++ decoder, format, tables and arithmetic backends are
unchanged from `4b399def`.** No additional decoder mode is required.

Against strong previous v5 incumbents, the default automatic result reduces
aggregate PCM SSE by **2.244% / 3.032%** in profiles 4/6, with no increase in
any selected full firmware image. These are numerical gains, not percentages
of perceived quality. Growth remains explicit and is screened separately.

## Search and corpus

The speech set contains 49 cases / 59 reset segments / 2,632,296 original-level
samples (329.037 s). It includes related levels, conditions and prepared material;
it is not 49 independent speakers or a held-out listening experiment. References,
complete joins, actual caps and strongest prior alternatives were checked.

The seed screen recomputes 500 previous whole-clip alternatives. For each
profile and exact 0/+5/+10% segment cap, it retains the best feasible previous
candidate preserving the original four PCM/PWM SSE/STOI floors. The 294 strong
incumbents include previously retained raw alternatives. New search never starts
from an artificially weakened pre-refinement seed.

`refine_speech_lpc.py` screens legal +/-1 ordered LSF coordinates with exact
integer synthesis. It patches the changed 320-sample compact frame plus the
following 160-sample interpolation dependency, carries filter/pitch state into
the full suffix, counts actual Rice gap/delta/repeat costs and serialized extra
markers/tails, then checks whole-reference quality. The original remains a
rollback; raw best-encountered PCM-SSE alternatives remain inspectable.

Bounds: 32 visited frames per reset segment, two spectral finalists, 640-sample
screening lookahead, 80-sample local excitation horizon, one pass. Both the joint
branch and a same-settings branch without local excitation refitting are run:
588 case/profile/budget variants, 708 segment fits. The latter can still reclaim
later optional pulses to pay spectral bit costs; it is not frozen excitation.

Neither branch wins uniformly. At the existing byte cap, further PCM SSE
reduction versus each strong previous incumbent is:

| Search branch | Profile 4 | Profile 6 |
| --- | ---: | ---: |
| Joint LPC and local excitation | 1.518% | 2.926% |
| LSF without local excitation refit | 2.078% | 2.198% |

Both branches and all previous alternatives enter automatic selection. This
bounded comparison does not establish a global optimum or superiority over
every possible equal-compute encoder search. Parallel shard times were about
269-284 s for joint and 347-357 s without local excitation refit; accepting more
small LSF moves can require more full metric evaluations. Timing depends on
host, warm caches and concurrent jobs, not only algorithm complexity.

[All 588 branch results](speech-results.csv), [independent quality receipts](quality-summary.json).

## Actual complete firmware cost

The new collector links one image for the entire ordered recording. Each
segment has exact distinct PROGMEM storage; pointer/length tables, segment
switching, startup, runtime, codec tables and retained IRQ/profiling code count
once. Full Flash is `.text + .data`, not ELF file size or a decoder estimate.
Exact array ranges/bytes and source/build/image identities bind each local
measurement. Unknown cost is never zero.

All **1188 distinct images** were linked for ATmega328P / AVR5 GNU ABI,
AVR-GCC 7.3.0, explicit ASM, 16 MHz / 8 kHz, queue512/prefill384,
`-Os -flto -mcall-prologues -mrelax`, unroll1/tuning0, speech+compact+v5-only.
Full image sizes are **5606-30926 B**, all within the explicit **32768 B** hard
limit. No bootloader reservation is assumed. Non-stream Flash is 5085-5336 B;
static SRAM is 1085-1086 B. Both vary with actual reset geometry/linking.

This complete-chain harness differs from the previous one-array 5063-5064 B
study. Its dispatcher and tables are real costs, not a decoder regression or
an isolated library-size measurement. Baseline and candidate images use the
same harness/compiler/geometry; alignment and known array lengths can change
non-stream cost by a byte. Corpus stream-byte totals are not one combined image.
The planned minimal production player remains a separate future stage.

[1774 measured candidate records](firmware-candidates.csv),
[source/toolchain/flags and aggregates](budget-summary.json),
[independent ELF/selection audit](selection-audit.json).

The size evidence was collected with the collector in `1110c59e`. A subsequent
host-side validation correction distinguishes the old runner's 64000-sample
decode-duration window from its complete output/underrun verification. It
changes no linked AVR source or recipe; the original images remain immutable
and were independently checked from their actual ELF sections and binary bytes.

## Automatic budget policies

`select_speech_budget.py` decodes complete chains against the full original
reference, validates native/model/PWM parity, and rejects mismatched source,
runtime, stream, reset-geometry or build evidence. Exact stream-cap ceiling is
`(bytes*(100+percent)+99)//100`; hard full-image growth limits round down.

Default `review` chooses the lowest PCM SSE among the measured no-growth
frontier choices that preserve baseline PCM/PWM SSE and available STOI. Further
ties use PWM SSE, full Flash, stream bytes and candidate ID. It keeps measured
Pareto growth alternatives for listening. Explicit `metric-proxy` may recommend
growth when either absolute STOI gain >=0.005 or SER gain >=0.25 dB passes in
both output domains, preserving the best no-growth choice's four floors. These
are configurable numerical thresholds, not validated audibility thresholds.
Both policies enforce 32768 B and <=10% full-image growth in this study.

| Profile / policy | Stream-byte sum | Further PCM SSE reduction | Mean PCM STOI gain | Growing images / 49 | Full Flash delta per image |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4 / default | 150962 -> 150952 | 2.244% | +0.001059 | 0 | -2..0 B |
| 6 / default | 216081 -> 216076 | 3.032% | +0.000913 | 0 | -4..0 B |
| 4 / explicit proxy | 150962 -> 152309 | 2.574% | +0.001689 | 6 | -2..+366 B |
| 6 / explicit proxy | 216081 -> 217991 | 3.518% | +0.001660 | 6 | -4..+516 B |

Default improves 47/49 profile4 and 46/49 profile6 cases, retaining the baseline
for the other five. It selects 47 joint, 46 no-local-refit and five baseline
choices across the 98 profile cases. A +5/+10 search cap is permission to spend,
not a required final size; some such candidates qualify at no full-image growth.
The baseline is the strong previous budget0 result. SSE aggregates use summed
error energies; STOI is the unweighted mean of the 49 full-case differences.
Peak error and other unoptimized fidelity properties can trade off.

The tool can also compare profiles under one budget. Starting from each strong
profile4 baseline, default retains the same no-growth result. Explicit proxy
switches five short cases to profile6 and grows ten images in total; maximum
full-image growth is 9.828%, not an automatic 10% spend on every clip. Aggregate
PCM SSE falls 7.849% and mean STOI rises 0.005711, with stream sum150962->154488 B.
This is numerical screening with a declared profile4 baseline, not the within-
profile incremental result above or listening confirmation.

For example, one 3.05 s anonymous clip switches from 1426 to2066 stream bytes:
full Flash6512->7152 B (+640 B /9.828%), PCM/PWM STOI gains about0.083 relative
to the best no-growth result. A 1.42 s clip uses739->1169 stream bytes and
full Flash5824->6254 B, with STOI gains about0.046. These are useful listening
candidates; they do not establish a general audible improvement.

[All 294 policy decisions](budget-selections.csv). A local six-case randomized
A/B/C pack compares the previous strong v5, no-growth selection and explicit
proxy recommendation in both PCM16 and fixed hardware PWM. It preserves full
length/level and verified WAV samples. Media and answer keys stay ignored;
no listener ratings were collected.

## Complete output with active IRQ

Every unique default/proxy selection, including cross-profile choices, was
simulated as its complete reset chain: **111 normal images** and **five heavy
controls with +100 cycles/audio IRQ**. All116 produce exact independent-model
PWM, complete sample/tick counts, zero decoder errors and zero underruns.
Observed minimum queue occupancy before producer EOF is384 samples and minimum
stack margin after ready is882 B. These are the measured workloads, not a
universal worst-case or physical-board claim.

The existing simavr runner records at most64000 decode durations. Output,
underruns, completion and stack observation cover the whole recording in every
case; raw decode-duration totals/maxima cover only the first64000 samples in
12 long controls and the complete chain in104. Each row explicitly reports
`decode_timing_samples`, `decode_timing_complete` and statistics scope. The
initial strict count check exposed this instrumentation limit; revalidation
preserved all complete-output checks and did not discard failed audio or
silently relabel partial duration statistics. A fresh synthetic64001-sample
end-to-end run additionally exercises the corrected validation.

[Full timing/PWM measurements and coverage](timing-measurements.json).
The portable C backend remains selectable and numerically covered; the earlier
finding that this AVR C recipe misses8kHz is not overturned by ASM-only timing.

## Verification and non-speech limits

All 181 frozen corpus cases /306 segments /1224 baseline+selected streams again
match the independent model, saved PCM16/PWM and both common/v5-only native
layouts. [Compatibility receipt](compatibility.json).

The separate non-speech robustness run covers132 cases /247 segments and both
profiles, using four visited LPC frames/reset and no growth:264 variants,
494 segment fits,124 numerical SSE improvements. Aggregate PCM SSE falls only
0.04284% /0.05039%; stream sums shrink24/30 B. Raw diagnostic choices preserve
PCM/PWM SSE but can lower STOI: only173/264 meet all four diagnostic floors.
STOI is not interpreted as music intelligibility; this is robustness evidence,
not a notable music-quality improvement or target Flash/timing admission for
long music. [All diagnostic branches](non-speech-results.csv),
[summary](non-speech-summary.json), [independent audit](non-speech-audit.json).

All47 targeted tests pass, including exact coefficient-tail/capacity checks,
rollback/raw alternatives, cached-evidence invalidation, protected output
aliases and end-to-end selection. Additional independent optimizer checks cover
52 randomized coefficient patches,216 exact capacity serializations and60
boundary fits with/without excitation refit and two passes. No decoder source
change requires a new compatibility mode or removes the portable C fallback.

## Reproduce and retain

Use [the tools workflow](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_COMPACT.md#joint-lpc-and-excitation-refinement)
and [complete-chain collector contract](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_FLASH.md#complete-recording-firmware-cost).
[Reproduction assets and protocol](reproduction/PROTOCOL.md) retain the exact
corpus search/audit scripts, source/runtime inventory, anonymous shard lists
and safe installer. The private canonical references and previous strong streams
are still needed for exact numerical replication; public hashes cannot recreate
them. A replacement corpus is a new experiment.

Private names, paths, per-recording source/PCM/stream/image fingerprints,
path-bearing manifests, media, firmware and logs are excluded from Git.
Source hashes and anonymous metrics remain reviewable. The saved
[development plan](../../V5_DEVELOPMENT_PLAN_RU.md) tracks completed stages1/2
and leaves the player, expanded listening, physical board and Tiny Period
experiments as later work.
