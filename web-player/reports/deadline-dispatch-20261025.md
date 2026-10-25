# Deadline cache lookup placement: retained for the measured rhythmic workload

Commit `741a1301` inlines the existing same-state cache check and keeps the full
scanner separate. Rhythmic physical capture measures 1.088x in the first screen
and 1.086x in longer confirmation on this host (6/8 and 7/8 pairs faster).
Other workload gains remain unproven, including possible small CLKI/watchdog
losses. No general/browser speedup or newly supported real-time profile is claimed.

## Change and correctness boundary

Baseline is `cf9c91f6`, native SHA `b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4`.
The retained native is 118,742 bytes (+671), SHA
`33cbb4e4b7b6727f510793e1149099a48c77692bc013755ae739edc4b650c02a`.
Clang 24/Binaryen 133, SDK 6.0.12, flags, source list, 109 function exports,
no host imports and fixed two-page memory/8192-byte stack limit remain the same.
Only device.c changes among compiled inputs; no state field or CPU ABI changes.

The scanner declaration gains `noinline`; the small wrapper gains `always_inline`.
Removing those declarations/qualifiers and their comment exactly recovers the
baseline C source. Scanner statements, cache key, fault handling, conversions
and every invalidation point are unchanged. In particular, the cache is cleared
before every time advance/service, including zero delta. This does not retain
hardware deadlines across time or omit clock phases or I/O publication.
The [current ownership audit](../native/deadline-dispatch-audit.md) extends the
original cache dependency map to CLKI and buffered continuations.

Both native images rebuild exactly before static comparison. The original
3,351-byte next_event body contains the scanner and reserves 16 native stack
bytes before testing a cache hit. In the new image that body disappears; the
scanner remains separately at 3,258 bytes, and its conditional calls replace
eight static wrapper calls. Four callers grow: advance_half_until_ps 2081→2463,
advance_to 332→530, device_next_cpu_event 198→291 and wait_until 603→694 bytes.
The other 198 bodies are identical. No working-memory saving is inferred from
source inlining or the removed wrapper prologue.

## Measurements and limits

Node 22.22.3 / V8 on Windows, Ryzen 5 5600X. All four labels receive the same
options, generated CPU bytes and ABI, default pin observations and fresh memory.
Modules are identical within oldA/oldB and newA/newB. The Williams schedule
balances positions and directed adjacent pairs. Each row uses eight measured
four-label trials and four full-workload warmups per label. Construction, source
hashing, snapshots and diagnostics are outside capture timers. Host load, CPU
frequency, GC and JIT tiering remain uncontrolled. No test/build/profile workload
runs alongside the speed measurements.

| Physical workload | First screen | Longer confirmation | Longer pairs faster |
| --- | ---: | ---: | ---: |
| Rhythmic | 1.088x | 1.086x | 7/8 |
| HQ4 | 1.031x | 1.037x | 5/8 |
| CLKI 20 MHz /1 kernel | 1.040x | 0.982x | 2/8 |
| Internal 20 MHz /1 kernel | 1.081x | 1.020x | 4/8 |
| Internal kernel, active ADC | 0.973x | 0.998x | 4/8 |
| Internal kernel, active watchdog ISR | 1.006x | 0.982x | 4/8 |

Screen intervals are 12,000 music frames /1,200 kernel frames at 48 kHz;
confirmation uses 48,000 /4,800. Total: 384 timings /192 warmups, 7,008 snapshots
and 6,862 comparisons. The separate 15-case parity matrix adds 30 executions,
176 snapshots and 88 comparisons: 7,184 snapshots /6,950 comparisons overall.
Every observation preserves exact PCM bytes, complete public/diagnostic state,
data/Flash/EEPROM/IRQ and retained pin history, with actual divisor, ADC and ISR
activation assertions. Histories consumed by native audio are not independent
captures of every physical edge; no silicon measurements are added.

Rhythmic's similar result across both intervals supports this small placement
tuning, with substantial variance: its longer pair range is 0.923–1.199x and
old/new identity medians are 1.044x/1.049x. HQ4 is faster in only 5/8 pairs and
its identity shifts are comparable to the small gain. Kernel identity variation
is larger still (e.g. long ADC old identity 0.873x); their small medians do not
establish gains or exclude small losses. Do not attribute all elapsed-time
changes to stack/call removal, or extrapolate across hosts/firmware. The native
runtime and JIT placement differ, while the hardware algorithm does not.

## Verification and replay

Focused scheduler/deadline/buffer tests pass 34/34. All 1,704 default and shared
music-tool tests pass, zero skips (113.16s). An isolated reconstruction from
pinned Git inputs also byte-matches the candidate and passes all 15 parity cases.
These checks, compilation and static diagnostics are separate from timing.

[Evidence](deadline-dispatch-20261025/) retains the C candidate, native binary
and manifest, exact static comparison/inventories/maps, relevant WAT bodies,
tools, both screens, parity and TAP. The verifier checks hashes and C-source
equivalence, per-run observations and paired statistics. Optional rebuild uses
a fresh ignored tree and leaves the production image untouched.

```sh
node web-player/reports/deadline-dispatch-20261025/replay.mjs
node web-player/reports/deadline-dispatch-20261025/replay.mjs --rebuild
node web-player/scripts/benchmark-runtime-controls.mjs --baseline-ref cf9c91f6 --change-set deadline-dispatch --validate-only --out build/deadline-check.json
node --test web-player/tests/*.test.mjs tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
```

The default engine stays `wasm`; the browser IRQ/underrun gate is not rerun.
The ATtiny13A plan remains 21/30 with nine open. The old idle-ADC synthetic
penalty is not declared resolved. Next audit recurring GPIO synchronizer/settled
queries before changing their activity policy; keep that experiment independent.

Primary references: [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[official DFP 3.4.278](../vendor/microchip/ATtiny_DFP/3.4.278/README.md),
[Clang attributes](https://clang.llvm.org/docs/AttributeReference.html#always-inline-force-inline),
[WebAssembly control instructions](https://webassembly.github.io/spec/core/binary/instructions.html#control-instructions).
Inspect final WASM: source attributes do not guarantee the result of later passes.
