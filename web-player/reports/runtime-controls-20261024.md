# Runtime controls and optimized event-service bodies

This follows the [long internal-phase correction](internal-audio-spans-20261024.md).
That correction fixes output-ring overflow, but its three-variant timing run
reported ordinary-workload regressions of up to roughly14%. This investigation
separates measurement controls from static code changes before accepting a new
optimization. Production device definitions, clocks and peripheral behavior
remain the correctness reference.

## Equal-policy controls

The [new runner](../scripts/benchmark-runtime-controls.mjs) uses oldA/oldB and
newA/newB. Each pair shares exactly one native Module object. All four labels
use the same host observation policy, firmware, CPU bytes, ABI and workload;
instances and memories are fresh. A Williams design and its reversed rows
balance positions and every directed adjacent pair. Each label receives four
discarded full-workload warmups. Three
[design tests](../tests/runtime-control-design.test.mjs) check those independent
count invariants, known-cost ratios and rejection of corrupt observations.

The unmodified precompiled loader creates a new generated-CPU Module on every
construction. The runner asserts this policy; it does not assume the supplied
`generated.module` is reused. Lowering, construction/compilation, input setup,
snapshots and comparisons remain outside execution timers. Native module
sharing and warmup counts are equal between versions. No guarantee of stable
engine tiering is inferred from warmup alone.

OldA/oldB and newA/newB are identity/null controls. Cross-version ratios use the
geometric mean of both old times divided by the geometric mean of both new
times within each trial. Exact PCM, CPU/device state and diagnostics, memories,
IRQ frames and host pin history are compared after every batch, including
warmups. These are coupled Node execution measurements, not exclusive
subsystem costs or browser real-time guarantees.

### Initial control and explicit-divisor repeat

The first [six-case run](runtime-controls-20261024/initial-six-case-controls.json)
uses the [initial harness](runtime-controls-20261024/initial-harness-source.txt).
Its `kernel-clki-20m-div1` fixture correctly ran at divide1 without a CLKPR
write. A temporary suspicion that it retained divide8 was wrong: the official
header defines CKDIV8 at bit4, not bit7, and low fuse0x70 leaves it unprogrammed.
Every initial raw record confirms the intended `clockDivisor`, including1.
No initial case is excluded. This source check uses the untouched
[manufacturer definition](../vendor/microchip/ATtiny_DFP/3.4.278/include/avr/iotn13a.h)
and [data-sheet section17.2](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=110).

The strengthened runner always requests the configured divisor, including1, and
asserts the completed actual divisor after each warmup and measured run. The
[explicit-divide1 repeat](runtime-controls-20261024/explicit-div1-repeat.json)
uses the [updated harness](runtime-controls-20261024/explicit-div1-harness-source.txt).
Its old/new identity medians are0.999/0.998; cross-version median is1.022.
Thus the earlier0.894x observation is not a stable divide1 regression under
these controls. Other identity controls show material variation, so neither
the initial three-way timing nor a changed function body alone proves a cause.
All raw observations and the correction to the mistaken suspicion are retained.

## Exact optimized-function comparison

The [static comparison tool](../scripts/compare-device-functions.mjs) rebuilds
each artifact from its exact manifest inputs with the pinned Clang and the same
wasm-opt -O3 pass. Every output byte must match the original artifact. Only a
diagnostic custom name section is appended before disassembly, and executable
sections must remain byte-identical. This follows the
[WASM binary module format](https://webassembly.github.io/spec/core/binary/modules.html)
and [custom name-section contract](https://webassembly.github.io/spec/core/appendix/custom.html).

Raw body hashes are recorded separately from symbol/type-normalized WAT
hashes. Only actual `(type $N)` uses receive structural-signature normalization;
local variables and labels with the same spelling retain their original
namespace. A built-in five-case self-test checks this collision, renamed type
indices and negative operand/type/nesting cases. Changed normalized text is
not a proof of semantic inequivalence, and equal caller bodies do not prove
equal callees. No performance is measured by this tool.

| Optimized symbol | 4f09550 bytes | c302a77 bytes | Single-service-inline candidate bytes |
|---|---:|---:|---:|
| advance_to | 3922 | 332 | 371 |
| advance_half_until_ps | 1259 | 2081 | 2120 |
| service | absent | 3586 | absent |
| clki_service | absent | absent | 3554 |

For4f09550→c302a77,127 bodies are raw-identical,64 differ only by symbol/type
relocations, two have changed normalized bodies, and `service` is added.
The unchanged C event loop therefore did change after optimization: its
formerly embedded service body becomes a call. That is static evidence, not
an attribution of the measured slowdown.

The candidate applies `always_inline` only to the `service` wrapper, using the
[Clang function attribute](https://clang.llvm.org/docs/AttributeReference.html#always-inline-force-inline).
The final WASM still outlines CLKI work into `clki_service`; it does not restore
the old3922-byte containing body. Against c302a77,155 bodies are raw-identical,
36 relocation-only, two changed, one added and one removed. The candidate
runtime is114638bytes (+46), SHA-256
`2c9b802c7ecb3a09c18c88ef1ec92ce67a0931ba7c0a52af29c18d46395867f6`.
It keeps105 function exports, zero imports and fixed two-page memory.

## Candidate acceptance

The single-wrapper inline candidate is rejected. Its13-case run contains832
timed executions,208 discarded warmups and6636 exact state/PCM checkpoints.
All comparisons pass, including actual clock divisors and enabled-ADC controls.
The125 focused checks also pass. Correctness therefore does not distinguish
the candidate, but the measurements establish no general execution-speed gain.

The following medians come from the retained
[raw candidate run](runtime-controls-20261024/service-inline-benchmark.json).
Cross-version values above1 favor the candidate. Identity values compare the
same binary and expose variation; neither column is a confidence interval.

| Case | Old identity | New identity | Cross-version ratio | New faster trials |
|---|---:|---:|---:|---:|
| rhythmic-compatible | 0.988 | 0.973 | 0.989x | 5/16 |
| rhythmic-physical | 1.033 | 1.031 | 0.959x | 7/16 |
| lumiere-stereo-compatible | 0.972 | 1.018 | 0.991x | 6/16 |
| lumiere-stereo-physical | 1.028 | 1.001 | 0.995x | 8/16 |
| hq4-chego-auto-compatible | 1.019 | 0.958 | 1.016x | 9/16 |
| hq4-chego-auto-physical | 1.018 | 1.180 | 1.086x | 12/16 |
| kernel-compatible-direct | 1.024 | 0.980 | 1.004x | 9/16 |
| kernel-physical-direct | 1.001 | 0.995 | 1.024x | 12/16 |
| kernel-clki-20m-div1 | 0.997 | 0.992 | 0.983x | 3/16 |
| kernel-clki-20m-div256 | 0.999 | 0.991 | 0.975x | 3/16 |
| kernel-internal-20m-div1 | 1.029 | 1.008 | 0.965x | 6/16 |
| kernel-internal-20m-div1-adc-active | 1.077 | 1.011 | 1.054x | 9/16 |
| kernel-clki-20m-div1-adc-active | 0.952 | 1.029 | 0.988x | 7/16 |

The largest firmware ratio,1.086x for HQ physical capture, accompanies a1.180
new-binary identity ratio. CLKI /1 and /256 favor the candidate in only3/16
trials each. These data do not justify keeping the inline hint or attributing
the earlier regression exclusively to outlining.

The initial and repeated controls add224 timed executions,112 warmups and1504
exact checkpoints. Across all three experiments there are1056 timed executions,
320 warmups and8140 checkpoints; ratios from different experiments are not
pooled into an overall speedup. The independent
[analysis script](runtime-controls-20261024/analyze-controls.mjs) rechecks raw
parity records, actual divisors, source hashes, scheduling and derived ratios.

The retained [source patch](runtime-controls-20261024/service-inline-device.patch),
[exact source](runtime-controls-20261024/service-inline-device.c.txt),
[manifest](runtime-controls-20261024/service-inline-native-manifest.json) and
[binary](runtime-controls-20261024/service-inline.wasm) reproduce the rejected
candidate in an ignored build directory without changing production files.
The isolated rebuild reproduced every byte. Static archives retain exact maps,
function inventories, normalization source and changed bodies for
[4f09550→c302a77](runtime-controls-20261024/before-correction/summary.json) and
[c302a77→candidate](runtime-controls-20261024/inline-candidate/summary.json).
Their `archive.json` files list retained paths; relocation-only body diffs remain
in the original ignored diagnostic directories, with hashes retained here.

Production C, WASM and manifest were restored exactly to `c302a77`:
114592 bytes, SHA-256
`95e52f9f724ef698a2fa15ac318728080af45b709afd0719ee9e3642048fa787`.
That exact core previously passed1302/1302 default tests. This checkpoint reruns
the three control-design tests and five static-normalizer self-checks; it does
not claim a new full-suite run for the rejected candidate.

```powershell
node --test web-player/tests/runtime-control-design.test.mjs
node web-player/scripts/compare-device-functions.mjs --self-test
node web-player/scripts/compare-device-functions.mjs --baseline-ref 4f09550 --candidate-ref c302a77
node web-player/reports/runtime-controls-20261024/analyze-controls.mjs
node web-player/reports/runtime-controls-20261024/rebuild-rejected-service.mjs
```

The archived final harness records the candidate benchmark invocation with
`--baseline-ref c302a77 --change-set service-inlining --trials 16 --warmups 4`.
That change-set assertion intentionally fails against the restored production
checkout; the archived candidate must be supplied to repeat that timing run.

The main plan remains21/30 complete. Exclusive subsystem timing, broader
activity gating, the real-time/default-engine gate, cache work and physical
chip acceptance stay open. There is no new silicon measurement or external
programming support in this checkpoint.
