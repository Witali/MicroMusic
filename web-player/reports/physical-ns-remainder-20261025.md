# Exact physical nanosecond remainder reduction

Retained in the full ATtiny13A native runtime. Physical-mode nanosecond
conversion now stores its fractional remainder as0..999 picoseconds. Generated
CPU bytes, original AVR cycles, source transitions, peripheral events and the
authoritative1ps timeline are unchanged. The default music engine stays `wasm`.

HQ4 physical execution improved1.103x in the first Node screen and1.164x in
an independent repeat, faster in all16 pairs. Other workloads do not establish
stable gains. A small internal20MHz-kernel regression remains possible; the
short-run negative medians weakened in the longer test and identity controls
are noisy. This is a workload-specific native-runtime improvement, not a
uniform speedup or a passing browser real-time profile.

## Representation and correctness

The old physical formula is
`floor((delta_ps * 1e9 + numerator_remainder) / 1e12)`. Initialization sets the
remainder to zero and fixes the physical time contract. Consequently that
remainder is always divisible by1e9. Store it divided by1e9 and evaluate:

```c
uint64_t whole = delta / 1000;
uint32_t tail = (uint32_t)(delta % 1000) + phase_ps;
if (tail >= 1000) { tail -= 1000; ++whole; }
```

The split is necessary: `delta + phase_ps` can overflow uint64. The tail is
at most1998 and the quotient increment fits. MCU reset and OSCCAL/CLKPR changes
preserve this time coordinate. New device initialization starts a fresh zero
epoch. A static assertion requires the existing1e12ps/second contract.

The NVM scanner converts the reduced remainder back to numerator units by
multiplying by1e9 before its general deadline formula. That product is below
1e12. Preserve ceil/deadline rounding and exact endpoint ties; do not pass a
picosecond remainder directly to a formula expecting numerator units. Legacy
nanosecond conversion, CPU/source phase and watchdog numerator remainders retain
their previous algorithms. No clocks are gated or skipped. The private field
remains uint64, so no working-memory saving is claimed.

Baseline: `0906621`, native SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.
Retained native SHA-256:
`953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0`.
Only `peripherals/device.c` changes among build inputs. Official Microchip
DFP3.4.278 definitions, compiler/options and109 function exports are unchanged.
The module grows117901→117975 bytes (+74); memory remains two fixed pages,
with8192-byte stack and no host imports. No handwritten assembly is introduced.

## Validation and code generation

All1677 Node tests pass, zero skips (78.84s). Three new actual-C/WASM tests
exercise8000 combinations of all1000 ps residues with native-width intervals,
including UINT64_MAX;2000 cumulative pseudorandom intervals;35 legacy fractions;
all8000 EEPROM/Flash residue/deadline combinations; and two overflow checks.
The isolated arithmetic fixture retains real `elapse` and scanner code, normally
resets the analog module, and does not stand in for source-edge/peripheral
service. The full suite also covers actual clock changes, resets, NVM1ps
completion boundaries, CPU phases, SPM, packages and active IRQs.

The complete13-workload untimed matrix retains26 runs/168 snapshots (84
cross-checks). Exact PCM, full architectural/diagnostic state, SRAM/Flash/EEPROM,
IRQ frames and pin history match baseline, including CLKI/divisors and enabled
ADC. No diagnostic observer is omitted. These establish model equivalence,
not unknown silicon phases or hardware timing calibration.

An isolated rebuild reproduces the retained binary byte-for-byte. Exact
optimized-WASM comparison finds201 identical bodies and two changed bodies:
`elapse`431→489 bytes and `next_event`3335→3351. The physical path replaces a
general ratio call with unsigned division by1000; Binaryen shares quotient and
remainder work. The legacy path also has different branching/register allocation.
These are static observations, not proof of a V8 cost or an explanation for
every measured difference.

## Timing scope and limitations

Windows/Ryzen5 5600X, Node22.22.3/V8, Clang24/Binaryen133 from the pinned
Emscripten6.0.12 SDK. CPU modules use unchanged direct-emitter bytes. Four labels
keep optional bounded regions and phase-local liveness disabled; no combined
speedup with those options is inferred. The four labels
use oldA/oldB and newA/newB native Module identity pairs, fresh CPU modules,
instances and memories, equal warmups and a balanced Williams/reversed schedule.
Each row uses eight trials and four warmups per label. Construction, snapshots
and hashing are outside timers; tests, builds and profiling do not run during
timing. Host load, affinity, frequency and GC are not controlled.

The first three-case screen plus the disjoint remaining ten-case matrix cover
all13 workloads. Real firmware renders12000 frames at48kHz with IRQs active;
direct kernels retire1M instructions; internal/CLKI kernels render1200 frames.

| Workload | Old/new median | Paired range |
| --- | ---: | ---: |
| rhythmic compatible | 1.082x | 0.979–1.177 |
| rhythmic physical | 1.078x | 1.012–1.163 |
| lumiere compatible | 1.010x | 0.962–1.049 |
| lumiere physical | 1.008x | 0.974–1.013 |
| HQ4 compatible | 1.044x | 0.997–1.058 |
| HQ4 physical | **1.103x** | **1.025–1.197** |
| kernel compatible direct | 1.004x | 0.748–1.043 |
| kernel physical direct | 0.981x | 0.887–1.076 |
| kernel CLKI20MHz /1 | 0.989x | 0.937–1.137 |
| kernel CLKI20MHz /256 | 1.008x | 0.952–1.104 |
| kernel internal20MHz /1 | 0.969x | 0.907–1.073 |
| kernel internal20MHz /1, active ADC | 1.008x | 0.955–1.105 |
| kernel CLKI20MHz /1, active ADC | 1.019x | 0.933–1.102 |

The repeat checks two real physical firmwares and both initially negative
kernels. Longer kernel runs then use10M instructions/12000 frames to reduce
short-interval sensitivity; `--kernel-frames` makes that workload explicit.

| Workload | First | Repeat | Longer kernel | Repeat faster pairs |
| --- | ---: | ---: | ---: | ---: |
| rhythmic physical | 1.078x | 1.028x | — | 5/8 |
| HQ4 physical | **1.103x** | **1.164x** | — | **8/8** |
| kernel physical direct | 0.981x | 0.998x | 1.040x | 4/8 |
| kernel internal20MHz /1 | 0.969x | 0.967x | 0.987x | 3/8 |

HQ4's repeat identity medians are0.994x/1.005x, with repeat cross-version range
1.076–1.346. The real-firmware HQ4 gain repeats in all16 pairs across both runs.
Rhythmic's large repeat variation does not establish its first gain. The
internal-kernel negative medians warrant retaining a possible small-regression
limitation, rather than claiming improvement everywhere: its long-run paired
range is0.796–1.294, with identity medians1.024x/1.038x and wider raw variation.
The long direct kernel also changes sign. No unproven slowdown is assigned a
compiler cause, and no uniform or cross-host guarantee follows.

All four timing invocations retain608 measured runs,304 warmups and5952 exact
snapshots (5828 comparisons against reference snapshots). The browser audio
gate is not rerun for this native revision. The previous
[live browser screen](bounded-browser-20261025.md) failed; neither these Node
ratios nor their combination with optional bounded regions establishes
underrun-free playback. The full-device plan remains21/30 with nine open items.

## Reproduce and continue

[Retained inputs and results](physical-ns-remainder-20261025/) include native
source/binary/manifest, test source/full TAP, both harness versions, all raw
trials and optimized-function diffs. Source hashes distinguish the initial
harness from its later configurable-kernel extension; no measured implementation
changes between runs.
The native implementation/tests are retained at `5411a35`; the final harness
is `e1f93ca`. Use these revisions for the commands below. The verifier checks
the archived native/test sources and long-harness snapshot against those Git
objects as well as the hashes recorded during execution.

```sh
node web-player/reports/physical-ns-remainder-20261025/verify-evidence.mjs
node web-player/reports/physical-ns-remainder-20261025/rebuild-candidate.mjs
node web-player/scripts/benchmark-runtime-controls.mjs --baseline-ref 0906621 --change-set ns-remainder --validate-only --out build/ns-check.json
node web-player/scripts/benchmark-runtime-controls.mjs --baseline-ref 0906621 --change-set ns-remainder --out build/ns-timing.json
node web-player/scripts/benchmark-runtime-controls.mjs --baseline-ref 0906621 --change-set ns-remainder --case kernel-physical-direct --case kernel-internal-20m-div1 --kernel-frames 12000 --instructions 10000000 --out build/ns-long.json
```

Next evaluate watchdog-period reduction separately only when its fixed base
frequency is exactly divisible by the configured watchdog frequency. Keep the
general path for other rates. Audit startup/reset pulse arithmetic and every
deadline consumer before changing that remainder's units; do not merely copy
the nanosecond substitution. Repeat the same state/pin/CLKI/ADC and performance
gates. This next candidate is unimplemented.

Primary references: [WASM unsigned arithmetic](https://webassembly.github.io/spec/core/exec/numerics.html),
[ATtiny13A data sheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and [pinned manufacturer definitions](../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
The device's documented clock/NVM timing parameters are preserved.
