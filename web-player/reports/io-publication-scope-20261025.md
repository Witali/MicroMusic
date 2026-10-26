# Scoped I/O publication: rejected performance experiment

The prototype preserves the tested execution semantics and removes configuration
publication work, but does not establish a general speed gain. Its longer
watchdog-active kernel is slower in seven of eight pairs (median 0.920x).
Production sources and WASM are restored to `69c40b97`, native SHA
`b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4`.
The default engine and hardware checklist remain unchanged: 21/30, nine open.
The earlier idle-ADC synthetic penalty remains a separate unresolved limitation.

## Implemented prototype and correctness

The [ownership audit](../native/io-publication-audit.md) identified 16 configuration
bytes among the 31 mirrored I/O bytes. The prototype splits their publication
from the remaining 15 dynamic bytes. Two optional native exports open/close an
explicit synchronous execution scope. Its first ordinary publication remains
full; later clock-only service reuses configuration. Bus writes, cross-register
effects, reset/power handling and other complete publication paths stay full.
Beginning/ending a scope does not normalize memory or advance time.

The host uses try/finally around each generated batch. A tiny WASM import adapter
validates exact native signatures, including return types, before use. Package
validation checks the same optional pair. Historical runtimes retain full
publication; `optimizeIOPublication:false` selects it on the prototype too.
There are two JS-to-WASM calls per batch and no WASM-to-JS callbacks per edge.
Generated CPU bytes, instruction cycles, shared CPU ABI and vendor maps are
unchanged. The candidate is 118,670 bytes (+599), with two one-byte scope flags,
two new function exports, no host imports and the original fixed two-page memory.
No working-memory saving is claimed.

All 1,711 prototype tests pass, zero skips (112.63s with tracing builds also
active). Fifteen new tests cover raw host mutation, zero-work/WAIT, direct native
and generated entry, partial instructions, cross-register effects, RESET/POR,
faults/traps, nested admission, absent/malformed capabilities and packages.
The 15-case production/candidate control matrix passes 30 executions and 88
snapshot comparisons, including internal/CLKI divisors and active ADC/watchdog.
These are model checks, not new silicon evidence.

## Timings and decision

Node 22.22.3 / V8 on Windows, Ryzen 5 5600X; Clang 24/Binaryen 133 from SDK
6.0.12. All labels share the current host wrapper, options, generated CPU bytes
and ABI. Only the candidate native supplies scope exports. Construction and
diagnostics are outside execution timers; begin/end calls are inside. The
four-label Williams schedule balances positions and directed adjacent pairs;
oldA/oldB and newA/newB are identical-module controls. Host load, GC, CPU
frequency and JIT tiering are uncontrolled. Sampling/counter time is excluded.

| Workload | First screen | Longer confirmation | Longer pairs faster |
| --- | ---: | ---: | ---: |
| Rhythmic physical | 1.048x | 1.023x | 6/8 |
| HQ4 physical | 1.016x | 1.042x | 6/8 |
| CLKI 20 MHz /1 kernel | 1.076x | 1.001x | 4/8 |
| Internal 20 MHz /1 kernel | 0.980x | 1.043x | 8/8 |
| Internal kernel, active ADC | — | 0.979x | 3/8 |
| Internal kernel, active watchdog ISR | — | 0.920x | 1/8 |

First screen: 12,000 music frames /1,200 kernel frames at 48 kHz. Confirmation:
48,000 /4,800 frames. Each row uses eight measured four-label trials and four
warmup passes per label. Together: 320 timings, 160 warmups, 6,816 snapshots and
6,674 comparisons; with the separate parity matrix, 6,992 snapshots /6,762
comparisons. Every observation matches PCM, complete CPU/device state and
diagnostics, SRAM/Flash/EEPROM/IRQ and retained pin history.

The small music medians coexist with substantial identity variation (long HQ4
old identity median 0.923x). The CLKI screen does not reproduce; the internal
kernel changes direction between screens. Its longer gain does not justify the
watchdog penalty and new execution-ownership protocol. Reject this implementation;
do not infer a universal cause from either the reduced stores or timing medians.
No browser IRQ/underrun gate was run or newly supported real-time profile claimed.

## Work removed and retained checks

Two seven-case diagnostic traces run the same candidate with scope on/off.
Both match their uninstrumented reference and each other on PCM/pin hashes;
service/dynamic publication counts remain equal. Examples of configuration
function entries, off→on: rhythmic 2,198,058→62,574; HQ4 2,274,529→25,565;
CLKI /1 1,300,802→2. These are source entries, not optimized WASM instruction
counts or a timing attribution. Removing work is insufficient speed evidence.

Eight independent public-memory boundary tests remain on the restored runtime:
zero-work and standalone generated calls, unknown CLKI/zero deadlines, RESET/POR
cancellation and release, fault boundaries and native-export restoration after
a WASM trap. Prototype-only capability tests stay in the evidence directory.
All 1,704 restored tests pass, zero skips (137.41s with the isolated replay also
active); `restored-full-test.tap` records this independently from the prototype.

The next candidate is repeated event/deadline scanning, starting with an ownership
and invalidation audit. Revisit publication only with a materially different
design and new balanced measurements. The existing 31-store public contract stays.

Retained diagnostic controls and boundary tests are committed at `8786f30a`.
The native baseline and every isolated replay input are pinned to `69c40b97`.

## Evidence and replay

[Evidence](io-publication-scope-20261025/) retains candidate native/host/package
sources, binary/manifest, prototype tests, control/tracer sources, both timing
screens, parity, both seven-case traces and TAP results. `replay.mjs` verifies
native inputs/hashes, all recorded state/PCM/pin identities, paired statistics and
trace counts. Its optional rebuild reconstructs an isolated ignored tree from
pinned Git inputs, byte-matches the native candidate, reruns its 15 focused tests
and the 15-case parity matrix without replacing production files.
This isolated rebuild also passed: the native bytes match, all 15 focused tests
pass, and all 15 parity cases reproduce. The retained replay log and parity file
record those extra checks; their executions are outside the timing totals above.

```sh
node web-player/reports/io-publication-scope-20261025/replay.mjs
node web-player/reports/io-publication-scope-20261025/replay.mjs --rebuild
node --test web-player/tests/*.test.mjs tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
```

Official register basis: [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and pinned [DFP 3.4.278](../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
Typed import validation follows [WebAssembly module instantiation](https://webassembly.github.io/spec/core/exec/modules.html).
Host shadow publication/ownership is an emulator API contract, not a silicon feature.
