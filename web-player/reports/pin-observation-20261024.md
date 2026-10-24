# Independent pin history and deferred native PCM collection

Implementation commit: `6b54398`.

The host pin trace and native PCM now have independent bounded queues. Reading
or clearing host history between audio batches cannot remove PWM transitions
needed by the next sample. Resumable collection can wait until a sample boundary
or queue pressure without changing the original clock advancement.

This is partial stage5 work in [ATTINY13A_PLAN.md](../native/ATTINY13A_PLAN.md),
not completion of peripheral activity scheduling or full silicon support. The
main checklist remains21/30 complete with nine open items. External programming
remains excluded; no physical chip capture or calibration was supplied.

## Reproduced defect

At baseline `d41ba7a`, two identical PWM cores captured one stereo frame, advanced
400 CPU cycles, and captured four more frames at48kHz. Draining only one core's
host history between batches removed five records from the shared PCM source.
Its next PCM values became `[-1,-1,-1,-1,...]` while the untouched core began
`[0.44,-0.36,0.36,-0.36,...]`; both CPUs still reached1000 cycles with identical
data memory. The [before](pin-observation-20261024/bug-before.json) and
[after](pin-observation-20261024/bug-after.json) observations retain exact
Float32 values. The runtime regression repeats this with legacy and physical
time, and also exercises timestamped GPIO inputs and external CLKI.

The corrected PCM ring retains PB1 levels for mono or PB0/PB1 levels for stereo.
Host history can independently select any PB0..PB5 metadata/level changes.
The [contract](../native/devices/attiny13a/pin-observation.md) specifies the
live baseline, same-timestamp snapshots, reset/subscription persistence,
legacy auto-discard and explicit retained-history ownership. Both queues hold
1024 records and fault explicitly on overflow. Unobserved pins still feed GPIO,
ADC/comparator, Timer0, IRQ and wakeup logic; source-clock phases are preserved.

## Why defer collection

The [eager-policy diagnostic trace](pin-observation-20261024/eager-policy-call-counts.json)
records1,892,526/1,676,575/2,095,317 `full_audio_collect` source entries for250ms
of physical rhythmic/lumiere-stereo/hq4-chego-auto. Many entries have no new pin events.
The private integrator accumulates integer high time, so constant-level spans
can be added later at the same exact sample endpoint.

Begin/sample completion always collect. Ordinary clock/wait calls remain eager;
resumable spans up to128 requested halves collect on pressure and also on native
BUFFER_READY. The watermark is total occupancy512, including wrap, in PCM or
legacy audio-owned host history. Retained host history cannot be freed by the
native consumer and is excluded from retry pressure; its capacity still faults.
Exceptional long resumable spans collect before entry to restore queue headroom, then
keep their original single advance and eager post-collection.
This does not add a generic overshoot guarantee for long nonresumable commands.
Fault prefix accounting, latched remaining work and reset ordering are unchanged.

## Validation scope

The final complete Node suite passed1276/1276 tests with zero failures or skips
in411668.8915ms, after restoring ordinary eager clock/wait collection and the
renderers' default observation policy.
The new68 checks comprise12 native queue/board cases,31 public
observer/runtime/package cases and25 pressure-policy cases. The latter compile
the exact current board and bridge with only the pressure query forced true,
thus obtaining an always-eager collection oracle without copying CPU semantics.
Both variants have fixed two-page memory and no host imports.

The earlier checkpoint passed1274 tests and416 timed runs but missed a queue
headroom regression. Two additional eager-first tests then failed on that
binary:400 NOP transitions followed by a700-cycle SPM barrier overflowed the
deferred queue even though the eager reference fit. Pre-collection before long
spans fixed both ordinary/resumable cases, including a second frame with wrapped
ring heads. All68 focused tests then passed. The earlier benchmark/source/patch
and test summary are retained under `pre-headroom-*`; they are not final
performance acceptance evidence.

The subsequent broad-pressure candidate is retained under `broad-pressure-*`.
It passed1276 tests and416 timed runs/2604 checkpoints, but the no-audio
compatible loop was slower than the eager two-ring control in8/8 pairs
(0.937x median), and two compatible firmware cases improved in only2/8 pairs
(0.951x/0.959x). The final implementation therefore restores ordinary eager
clock/wait collection and folds the long-phase pre-collection into the existing
audio-active advance branch. Pressure collection remains in the resumable
physical path. The final timings below evaluate that actual implementation.

Comparisons include exact raw PCM, complete public and private CPU diagnostic
state, data/Flash/EEPROM, IRQ frames and Flash generation. Cases cover mono and
stereo rates, sample ties, maximum-rate CTC through repeated queue wrap,
Timer0 ISR/RETI, watchdog sleep/wake, RESET during OUT, EEPROM read stalls and
completion,160/700-cycle SPM commands, Flash erase/retranslation, partial/held CLKI
at D1/D256 and ordinary fault prefix time accounting. A separate native test
compares the entire private board state, excluding only observer queues, with
active GPIO/ADC3/Timer/IRQ consumers and full versus disabled host observation.
Original package v1/v3 binaries retain their legacy fallback.

The final runtime also executes all22 [CPU acquisition profiles](pin-observation-20261024/cpu-probes.json)
with114 RESET cuts (136 actual-image runs) and all25 [CLKPR/RESET/ADC profiles](pin-observation-20261024/hardware-probes.json).
The [comparison](pin-observation-20261024/probe-compatibility.json) verifies exact
prior image hashes, raw CSV waveforms, every decoded field/marker and timestamp.
Decoded JSON fingerprints differ only because they include the new acquisition
output path; the [verifier](pin-observation-20261024/verify-probe-compatibility.mjs)
checks both recorded file hashes and every parsed field except that path. No
chip timing or state is normalized. All are synthetic software controls.
The helper expects the retained baseline and candidate acquisition directories;
a fresh checkout must regenerate those controls in the corresponding revisions.

The full suite is recorded in [test-summary.txt](pin-observation-20261024/test-summary.txt).
These are software/model checks; they do not resolve undocumented silicon
phases, Timer0 TOP=0, analog calibration or debugWIRE.

## Reproducible performance method

Baseline is `d41ba7a` with112674-byte native runtime, SHA-256
`d7be3a7378d14c2896a92106291715ed8fcb0d291359e5153efb639f9c18e0a8`.
The [initial eager two-ring manifest](pin-observation-20261024/initial-native-manifest.json)
identifies113637 bytes and SHA-256
`5f1ea0b36efc3526ae7635b0f6ae66730c798f0f08dd79c7023f7e3753f42b0e`.
Its exact [native patch](pin-observation-20261024/initial-native.patch) and
[rebuild script](pin-observation-20261024/rebuild-initial.mjs) reproduce that
binary from the baseline without editing production sources.

The final native runtime is113771 bytes, SHA-256
`794f8f961e8bf89ad2649c2fa470ea60fac0802f671395b3205504a740a94a4e`.
It retains fixed two-page memory and no host imports, with105 function exports
plus exported memory. The two new optional exports configure/report host
observation; generated CPU imports, continuation ABI and package format are
unchanged. The source/manifest checks verify unchanged compiler, native build
flags, manufacturer definitions and the exact four changed native inputs.

The final comparison uses four variants: original baseline, initial eager
two-ring runtime with full trace, final pressure-based runtime with full trace,
and the same final runtime with host mask0. Ordinary clocks remain eager;
pressure collection is restricted to resumable physical execution. Eight serial trials rotate/reverse
order so every variant occupies each position twice. Every case/variant has a
discarded warmup and fresh mutable state. Timing includes only public run or
capture calls, including batch copies. Generation/compilation, construction,
input submission, hashes and equality checks are outside the measured calls.

Cases cover six real firmware excerpts (three images × compatible/physical),
two direct million-instruction loops, internal20MHz and CLKI20MHz D1/D256,
plus two enabled-ADC controls. Firmware capture is250ms at48kHz; clock kernels
are25ms. ADC3 controls retain live conversions. Exact full chip observations,
raw CPU diagnostics, all memories, IRQ frames and PCM are compared at every
1024-frame endpoint. Full/default trace tails must match; host mask0 explicitly
omits only history after capture, preserving already-queued initialization rows.
No clock-state or deadline normalization is permitted.

The [initial312-run measurement](pin-observation-20261024/initial-benchmark.json)
and its [exact harness](pin-observation-20261024/benchmark-source.txt) are
retained as an earlier checkpoint. Its mixed results did not establish a
general observation-filtering speedup. Compare variants within one retained
run; do not divide timings from different checkpoints to attribute a change.

Node22.22.3/V8 12.4.254.21-node.56 on AMD Ryzen5 5600X, Windows10.0.26300.
Tests, builds and diagnostic counters do not overlap timed performance runs.
Host scheduling/frequency, GC and tiering remain uncontrolled. These are coupled
CPU/peripheral/pin/PCM measurements, not exclusive subsystem timings or browser
real-time/latency guarantees. Reduced entry counts alone are not speed evidence.

## Native source-entry evidence

The [default trace](pin-observation-20261024/call-counts.json),
[physical trace](pin-observation-20261024/physical-call-counts.json) and
[forced eager-policy trace](pin-observation-20261024/eager-policy-call-counts.json)
match production raw PCM and complete public/CPU/memory/IRQ observations in
all15 diagnostic cases. Eager policy forces only the copied public pressure
query true; it does not replace the board or CPU. Instrumentation exists only in ignored build copies and is
excluded from performance timing. Counts include source entries subsequently
inlined by O3; they are not WASM-call counts or exclusive elapsed times.

| Case | Forced eager-policy collection entries | Final collection entries |
| --- | ---: | ---: |
| rhythmic-physical | 1892526 | 12012 |
| lumiere-stereo-physical | 1676575 | 12012 |
| hq4-chego-auto-physical | 2095317 | 12012 |
| kernel-clki-20m-div1 | 702005 | 2402 |
| kernel-clki-20m-div256 | 5530 | 2402 |

All hardware-work entry counts match the eager policy on the three physical
music cases; only collector entries and its integer `ratio` conversions change.
Ordinary compatible music retains its initial eager entry counts.
CLKI helper retry/deadline counts change with the collection
frontier; each CLKI case still performs1000000 pin-voltage and analog-input
updates. `next_event_scan`, `mirror` and `clki_service` counts also match their
initial hardware-work counts. No source transition was removed to obtain the
lower collector count.

The fresh [baseline sampling profile](pin-observation-20261024/baseline-profile/summary.json)
retains three production-equivalent CLKI D256 runs, raw inspector profiles and
function maps. Its585 work samples still show source/scheduler and analog
costs; inlining prevents a precise exclusive pin-collector attribution. It is
context for selecting the experiment, not a percentage-speedup prediction.


## Final paired results

The [raw final measurement](pin-observation-20261024/benchmark.json) records416
timed executions and2604 exact pairwise state/PCM checkpoints. Its
[exact harness](pin-observation-20261024/final-benchmark-source.txt) matches the
recorded source hash. All checks passed at implementation commit6b54398.
No diagnostic build, probe or regression test ran concurrently with these timings.

Times are independent medians in milliseconds. Ratios are medians of individual
paired ratios, not divisions of those time medians. Phase=eager-full/final-full;
total=original baseline/final-full. Ordinary cases retain eager collection and
serve as controls for native layout and host variation; their phase column
does not represent an enabled pressure optimization.

| Case | Baseline ms | Eager two-ring ms | Final full-trace ms | Phase paired | Total paired | Total min–max | Total faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rhythmic-compatible | 655.45 | 604.76 | 663.75 | 1.007x | 1.019x | 0.935–1.282 | 4/8 |
| rhythmic-physical | 1071.36 | 909.20 | 833.01 | 1.217x | 1.165x | 0.981–2.239 | 7/8 |
| lumiere-stereo-compatible | 538.92 | 537.52 | 528.86 | 1.023x | 1.026x | 0.991–1.130 | 6/8 |
| lumiere-stereo-physical | 857.22 | 799.09 | 753.99 | 1.102x | 1.145x | 1.039–1.291 | 8/8 |
| hq4-chego-auto-compatible | 870.71 | 813.54 | 849.63 | 0.978x | 1.016x | 0.918–1.272 | 4/8 |
| hq4-chego-auto-physical | 1007.81 | 957.43 | 883.25 | 1.085x | 1.148x | 1.047–1.364 | 8/8 |
| kernel-compatible-direct | 312.74 | 309.06 | 327.99 | 0.950x | 0.960x | 0.742–1.285 | 3/8 |
| kernel-physical-direct | 206.08 | 199.54 | 216.34 | 0.920x | 0.928x | 0.758–1.240 | 3/8 |
| kernel-internal-20m-div1 | 104.36 | 95.28 | 80.55 | 1.182x | 1.233x | 0.796–1.554 | 7/8 |
| kernel-clki-20m-div1 | 698.45 | 690.44 | 642.86 | 1.054x | 1.101x | 0.850–1.227 | 7/8 |
| kernel-clki-20m-div256 | 407.65 | 421.72 | 409.69 | 0.984x | 0.989x | 0.873–1.077 | 2/8 |
| kernel-internal-20m-div1-adc-active | 101.40 | 98.72 | 93.78 | 1.044x | 1.064x | 0.943–1.206 | 7/8 |
| kernel-clki-20m-div1-adc-active | 669.87 | 701.75 | 681.48 | 1.040x | 1.011x | 0.841–1.114 | 4/8 |

For the three physical audio excerpts, the total median paired ratios are
1.145–1.165x, positive in23/24 individual pairs; phase collection versus the
eager two-ring control is1.085–1.217x, positive in21/24. This supports retaining
the resumable audio change on these workloads. It is not a general CPU-speed
claim: direct compatible/physical loops have0.960x/0.928x total medians, each
faster in only3/8 pairs, and CLKI D256 is0.989x. Broad pair ranges and differences
between successive checkpoints show substantial host variation. Ordinary CPU
collection remains unchanged in source; direct-run cost/layout attribution
needs a separate experiment. Do not describe every firmware or clock mode as
faster, or reuse synthetic ratios as browser guarantees.

The final observation-only medians also vary by workload (the raw file retains
every mask0 trial). Automatic renderer opt-out is therefore not retained;
explicit subscriptions remain available and renderers respect existing observers.
At the measured physical excerpt medians,250ms of sound still takes754–883ms,
so real-time acceptance and the default-engine switch remain open.

Reproduce after this report/tooling commit, retaining implementation6b54398 and
the recorded SDK:

```text
node web-player/reports/pin-observation-20261024/rebuild-initial.mjs
node web-player/scripts/benchmark-pin-observation.mjs --eager-dir build/pin-observation-initial-rebuilt --trials 8 --frames 12000 --instructions 1000000 --out build/benchmarks/pin-observation-phase-final.json
node web-player/scripts/trace-device-calls.mjs --physical-firmware --out-dir build/traces/pin-observation-phase-physical-final-20261024
node web-player/scripts/trace-device-calls.mjs --physical-firmware --eager-collector --out-dir build/traces/pin-observation-phase-eager-final-20261024
```

The next software work remains in the existing plan: attribute the direct-run
controls, investigate continuation/context and dispatch costs, and consider
broader peripheral activity only with exact dependency/phase proofs. Current
fixed-source long-span bounded-history limits remain documented; no silicon
measurement item is closed by these timing or parity results.
