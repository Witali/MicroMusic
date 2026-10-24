# Disabled-ADC scheduling experiments, 2026-10-24

Two ADC activity implementations preserved model behavior but did not pass the
measured-benefit gate. Both are retained below as experiments; production
`analog.c`, tests and native WASM were restored to `38f73db`. The retained
runtime remains 112668 bytes with SHA-256
`9a3461976f84d456ca6f2a1c8b2a24f0b1dadbc85ced2c45d20f1eeffbbc2bde`.
Disabled-ADC recurring-service omission is not enabled in production.

The first implementation removes millions of ADC entries but slows the active
internal-clock ADC control in every pair (median0.942x). A second implementation
selects enabled/disabled loops once on entry; it still slows rhythmic physical
capture in every pair (median0.915x, range0.907–0.920). Other cases vary widely.
These results do not justify keeping either implementation as an optimization.

## Implementations and correctness evidence

Both candidates omit recurring ADC advancement/deadline queries only with
ADEN clear. Timestamped bus, input, reference, trigger, acknowledgement and
clock/sleep APIs still catch up before mutation. Comparator advancement remains
the combined scheduler's monotonic-time anchor. ADIF/ADIE and trigger levels
remain live independently of ADC activity; ACME input routing remains intact.
See the [audited contract](../native/devices/attiny13a/analog-activity.md).

The hardware constraints follow [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections7.5.2/13.1/14.5/14.12.2: disabling ADC terminates conversion and resets
its prescaler; while enabled, prescaler phase continues between conversions.
ADC multiplexed comparator inputs and interrupt flags require separate handling.
The existing explicit digital timing choices are unchanged.

The [initial source](adc-activity-20261024/initial-analog-source.txt) caches ADEN
at entry but checks activity again inside deadline queries and branches around
ADC advancement. The [split source](adc-activity-20261024/split-analog-source.txt)
uses one entry decision: an unconditional enabled loop and a comparator-only
disabled loop. Public deadline queries still select the required components.
Only `analog.c` changes among native manifest inputs; compiler source,
dependencies, flags and exports remain equal to the baseline.

The initial candidate passed [1216/1216 integration tests](adc-activity-20261024/initial-test-summary.txt).
The split candidate passed [108/108 focused tests](adc-activity-20261024/split-focused-summary.txt),
including all29 new unconditional-reference checks, and all benchmark/trace
comparisons. A second full integration run was unnecessary after its speed gate
failed and production was restored; no full-suite claim is made for that source.

The [activity test source](adc-activity-20261024/activity-test-source.txt) builds
an unconditional-service reference by forcing the activity predicate true.
Complete private state is compared after catching up copies of disabled ADC
state with the original component function. No phase/origin fields are removed,
and production state is never settled solely for assertions. The
[pin-propagation oracle adaptation](adc-activity-20261024/propagation-test-source.txt)
uses the same rule. Coverage includes all eight prescaler encodings, both
half phases, abort/reenable, enabled idle phase, locked results, ADIF/ADIE,
held/changing triggers, ACME, clock/sleep gates, reference changes and voltage
mutation exactly at sampling time. Addresses come from manufacturer-derived
register definitions. These candidate-only tests are archived rather than left
in the active suite after restoration.

## Measurements

Baseline: `38f73db` (native runtime equals `ad66d6d`). Candidates were measured
from that worktree with source identities pinned in each raw report. Initial
native:112820 bytes, SHA-256
`54cb70075c7bf33f4566a1ef7fdea6ddad7169a7f9e47e9135878fad1c60be9a`.
Split native:112903 bytes, SHA-256
`3b1dbd3c22e6265b53ddae79cbf7a64c93fcdf1201c6ad95536ff3a584e21adf`.
All have no imports, fixed two-page memory,103 function exports plus memory.
Archived analog source hashes match their raw native manifests. The same
[exact harness](adc-activity-20261024/initial-benchmark-source.txt) was used for
both runs; its hash is checked against both reports.

Restore the selected archived analog source as
`web-player/native/peripherals/analog.c` on the baseline, build with
`node web-player/scripts/build-device-wasm.mjs`, and restore the archived harness
as `web-player/scripts/benchmark-planned-optimizations.mjs`. Run:

```powershell
node web-player/scripts/benchmark-planned-optimizations.mjs --native-only --baseline-ref 38f73db --trials 8 --frames 12000 --instructions 1000000 --out build/benchmarks/adc-activity.json
```

To repeat the candidate tests, restore the two archived test sources as
`web-player/tests/analog-adc-activity.test.mjs` and
`web-player/tests/device-analog-propagation.test.mjs`, then run the first file
for the29 new checks, or `node --test web-player/tests/*.test.mjs` for integration.

Each run contains240 timed executions:15 cases, two variants, eight alternating
AB/BA pairs, discarded warmups and fresh mutable instances. Firmware captures
are250ms at48kHz; direct kernels retire one million instructions; clock cases
capture25ms at20MHz. Two additional controls enable free-running ADC3 with
ADCSRA=0xe7, ADMUX=3, CLKPR=0 and a156.25kHz ADC clock. ADEN and ADIF must remain
set after completed conversions, with IRQs masked by ADIE=0.

The [initial data](adc-activity-20261024/initial-benchmark.json) and
[split data](adc-activity-20261024/split-benchmark.json) retain all individual
times, order, variance and generation/compilation observations. Timers include
public execution/capture only. Compilation, construction, input submission,
snapshots, assertions and hashes are outside them. Startup numbers are single
diagnostics; the loader also constructs a module outside the execution timer.
Project tests and diagnostic builds did not overlap timing. Host scheduling,
frequency, tiering and GC remain uncontrolled; the large run-to-run and
within-pair variation is retained, not filtered. Host:Ryzen5 5600X,
Windows10.0.26300, Node22.22.3, V8 12.4.254.21-node.56.

Median paired baseline/candidate ratios follow. Greater than1 means faster.
The reports contain min/max and every pair; do not pool these two experiments
or infer a gain from an isolated positive case.

| Case | Initial | Split |
|---|---:|---:|
| rhythmic-compatible | 0.976x | 1.031x |
| rhythmic-physical | 0.989x | 0.915x |
| lumiere-stereo-compatible | 1.028x | 1.025x |
| lumiere-stereo-physical | 1.040x | 0.932x |
| hq4-chego-auto-compatible | 1.086x | 0.987x |
| hq4-chego-auto-physical | 0.958x | 0.982x |
| kernel-compatible-direct | 0.990x | 0.991x |
| kernel-physical-direct | 0.957x | 0.950x |
| kernel-register-span-compatible-direct | 0.984x | 1.159x |
| kernel-register-span-physical-direct | 0.949x | 1.059x |
| kernel-internal-20m-div1 | 0.992x | 1.002x |
| kernel-clki-20m-div1 | 0.990x | 1.002x |
| kernel-clki-20m-div256 | 1.078x | 1.002x |
| kernel-internal-20m-div1-adc-active | 0.942x | 0.961x |
| kernel-clki-20m-div1-adc-active | 0.999x | 0.957x |

Each report validates688 pairwise checkpoints (1376 total), exact public state
and all diagnostics, register/data/Flash/EEPROM/IRQ-frame contents, raw Float32
PCM and remaining pin events. No scheduling hint or chip state is normalized
in these whole-device comparisons. Each also matches2001 pin events over2000
unequal CLKI transitions with ADC3 and both PWM outputs. Equality establishes
the implemented profile's behavior, not silicon measurements.

## Removed source entries

The [split counter trace](adc-activity-20261024/call-counts-and-prefix.json)
matches its production candidate. Its baseline is the retained
[guarded-block/NVM trace](planned-optimizations-20261024/call-counts-and-prefix.json),
whose native runtime hash equals the benchmark baseline. These are source
entries, including functions the compiler may inline, rather than elapsed cost
or necessarily actual WASM calls.

| Case | ADC advance before → candidate | ADC deadline query before → candidate |
|---|---:|---:|
| rhythmic | 2939289 → 37494 | 4369404 → 0 |
| lumiere-stereo | 2843741 → 37497 | 4196009 → 0 |
| hq4-chego-auto | 4061561 → 37497 | 6037169 → 0 |
| CLKI /1 | 5601604 → 1000000 | 5902407 → 0 |
| CLKI /256 | 5003948 → 1000000 | 5005923 → 0 |

Comparator advances, ADC source/input entries and emulated cycles are unchanged.
The million retained CLKI ADC inputs observe PB3/ADC3 transitions. Firmware
trigger updates and observations retain their required catch-up calls. This
proves that recurring work disappeared; it does not prove that dispatch and
generated-machine-code costs improved.

## Decision

Neither candidate is retained. Both sources, test adaptations and measurements
remain reproducible; active production files match the baseline. Do not repeat
isolated per-call ADC guards without new evidence explaining their cost. Broader
module scheduling, register caching and future compiler changes need active
workload controls as well as disabled-module call counts. Improve isolation and
cost attribution before claiming small gains from noisy timings. No coverage,
hardware-measurement or default-engine acceptance item is closed by this work.
After restoration, [61 focused checks](adc-activity-20261024/restored-test-summary.txt)
passed, and source/binary comparison confirms the retained compiler, peripheral
implementation and runtime equal the previously tested baseline.
