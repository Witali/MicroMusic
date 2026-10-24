# Streaming long internal-clock phases without losing pin history

Long resumable SPM phases can now drain their native output queues internally
instead of overflowing within one clock advance. CPU phases, hardware events
and audio integration retain their original time grid. This is a correctness
fix; performance comparisons below concern the ordinary workloads that both
runtime versions can execute.

## Reproduced defect and independent reference

The previous113771-byte runtime at `4f09550`, SHA-256
`794f8f961e8bf89ad2649c2fa470ea60fac0802f671395b3205504a740a94a4e`,
restored entry headroom before exceptional long phases. One advance could still
produce more than1024 transitions before returning to the PCM consumer.

The fixture executes SPM, then INC r20 and a self-loop. Its explicit model
parameter `spmCommandCycles:4800` stretches the command phase; it is not a claim
about silicon SPM duration. Timer0 CTC uses OCR0A=0, COM0A=toggle and no
prescaling, with PB0 configured as an output. This maximum toggle frequency
follows [Microchip DS40002307A, section11.7.2](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=71).
At9.6MHz/8kHz or20MHz/8kHz, one audio frame contains1200 or2500 transitions.

The [reproduction script](internal-audio-spans-20261024/reproduce-overflow.mjs)
loads the exact old WASM from Git and runs the current12-case regression.
Six cases fail with peripheral fault9/detail1024; six controls pass. The failed
cases cover the private stereo PCM queue with host mask0, the legacy host queue
with mono audio, and both histories together, at both low-rate clock settings.
The9MHz/11025Hz cases additionally exercise a fractional sample grid.

The reference advances the actual generated CPU and native board in short
3us observation slices, drains the complete physical host trace, and integrates
PB0/PB1 with integer high times on the exact audio grid. It has no native audio
subscription, private PCM history or collector. It neither duplicates CPU
instruction semantics nor relies on the eager-collection override, which also
overflows inside a single sufficiently long native call.

Each sample compares exact Float32 PCM, complete public state and Float64 CPU
diagnostics, register/I/O/SRAM bytes, Flash, EEPROM and IRQ frames. The first
sample leaves SPM unretired; after the long phase, INC r20 executes exactly once.

## Change and boundaries

`device.c` selects a separate event loop only for buffered internal-source
requests longer than128 half periods. At512 queued records it returns
BUFFER_READY after every event at the current timestamp has settled. The native
bridge drains its existing PCM/legacy-host histories and resumes only the
remaining half periods. No instruction effect is replayed and no JavaScript
callback is added.

The ordinary event loop, short internal requests, existing CLKI behavior,
nonresumable clock calls, observer ownership and compiler are unchanged. The
rare loop deliberately retains the original advance target on an ordinary
peripheral fault; calling the ordinary loop once per event would shorten that
fault endpoint. Reset still stops at its event, and completion/wall/pressure
ties preserve the documented continuation contract.

The14 native boundary tests also compare exact pin records and the complete
private board snapshot with the ordinary unbuffered path. Only consumed ring
storage and head/count bookkeeping are excluded from that snapshot. Clock
remainders, cached deadline, all peripheral/source state and live pins remain
in the comparison. Cases cover prefilled zero-progress yields,1ps fractional
boundaries, wrapped total occupancy, same-time input/reset, a CLKPR transition,
retained host history, an EEPROM fault after the first drainage and a zero tail
during actual BOD recovery.

The new runtime is114592bytes (+821), SHA-256
`95e52f9f724ef698a2fa15ac318728080af45b709afd0719ee9e3642048fa787`.
It retains16 C sources,105 function exports plus memory, zero imports,
fixed two-page memory and an8192-byte stack. Only `device.c`/`device.h` native
build inputs change. Manufacturer definitions and generated CPU code remain
unchanged.

## Verification

The final complete Node suite passes1302/1302 with zero failures/skips
(300929.5866ms). The [full TAP](internal-audio-spans-20261024/full-suite.tap)
includes all26 new checks:12 independent trace/PCM cases and14 native boundary
cases. The [old-runtime TAP](internal-audio-spans-20261024/baseline.tap) retains
six expected overflows; the [standalone trace-oracle TAP](internal-audio-spans-20261024/trace-oracle.tap)
retains12 passes. The production [manifest](internal-audio-spans-20261024/device-build.json)
records exact source/artifact hashes. Implementation, tests and runtime are
committed as `c302a77`.

```powershell
node web-player/reports/internal-audio-spans-20261024/reproduce-overflow.mjs
node --test web-player/tests/attiny13a-long-audio-span.test.mjs
node --test web-player/tests/device-internal-buffered-span.test.mjs
node --test web-player/tests/*.test.mjs
```

## Serial performance control

All312 measured runs and1932 exact state/PCM checkpoints pass. The
[raw benchmark](internal-audio-spans-20261024/benchmark.json),
[exact harness](internal-audio-spans-20261024/benchmark-source.txt) and
[validation summary](internal-audio-spans-20261024/validation-summary.json)
retain all trials and source/runtime identities. The comparison uses the same
13 workloads, eight trials and three variants as the preceding pin-observation
experiment, with the baseline changed to the immediate predecessor.

| Case | Baseline ms | Corrected ms | Paired ratio | Faster pairs |
|---|---:|---:|---:|---:|
| rhythmic-compatible | 253.67 | 266.69 | 0.946x | 0/8 |
| rhythmic-physical | 451.16 | 512.18 | 1.015x | 5/8 |
| lumiere-stereo-compatible | 377.09 | 395.01 | 0.944x | 2/8 |
| lumiere-stereo-physical | 537.35 | 561.95 | 0.960x | 2/8 |
| hq4-chego-auto-compatible | 575.49 | 588.09 | 0.988x | 1/8 |
| hq4-chego-auto-physical | 659.72 | 678.87 | 0.938x | 2/8 |
| kernel-compatible-direct | 207.66 | 207.53 | 0.986x | 3/8 |
| kernel-physical-direct | 132.87 | 126.95 | 1.062x | 7/8 |
| kernel-internal-20m-div1 | 60.29 | 55.35 | 1.077x | 5/8 |
| kernel-clki-20m-div1 | 407.29 | 447.07 | 0.894x | 1/8 |
| kernel-clki-20m-div256 | 270.26 | 306.18 | 0.880x | 1/8 |
| kernel-internal-20m-div1-adc-active | 44.24 | 44.81 | 0.975x | 1/8 |
| kernel-clki-20m-div1-adc-active | 303.19 | 311.18 | 0.931x | 1/8 |

Times are separate medians of each variant's elapsed milliseconds. The paired
ratio is the median of eight within-trial baseline/candidate ratios; it is not
the ratio of those two aggregate medians. Values above1 favor the correction.
Music uses12000 frames at48kHz (250ms); direct kernels execute one million
instructions, and20MHz captures use1200 frames (25ms). Audio-only variant
measurements remain in the raw data; the table compares unchanged default
observers.

There is no general speed improvement. Rhythmic compatible execution is slower
in8/8 pairs (0.946x), and CLKI /1 and /256 are slower in7/8 each
(0.894x/0.880x). The latter is roughly14% more elapsed time. Several rows have
large outliers; for example, internal20MHz paired ratios range0.631–3.815x.
Retain the correctness fix because the predecessor cannot execute the failing
long-span cases, but leave ordinary execution cost and the default-engine gate
open. Do not multiply these ratios by earlier, separately measured speedups.

A follow-up build forced `advance_halves_buffered_long` to be `noinline`.
Its WASM is byte-identical to the retained correction, so it cannot explain or
remove the measured cost. The [probe patch](internal-audio-spans-20261024/noinline-probe.patch)
and [probe manifest](internal-audio-spans-20261024/noinline-probe-manifest.json)
are retained; the production source/manifest were restored exactly to `c302a77`.
No additional timing or test repetition was needed for an identical binary.
Some affected workloads never enter the new long internal-span loop. Next,
separate ordinary continuation cost from module/code-layout and host variation,
using identical-runtime controls and fresh execution profiles before another
fine-grained guard or register-local experiment.

```powershell
node web-player/scripts/benchmark-pin-observation.mjs --baseline-ref 4f09550 --change-set long-internal-span --trials 8 --frames 12000 --instructions 1000000 --out web-player/reports/internal-audio-spans-20261024/benchmark.json
```

The audited change-set option checks exact manifest hashes, unchanged compiler,
exports, flags, memory geometry and the two expected native inputs. Generation,
compilation, construction, snapshots and parity checks stay outside execution
timers. Baseline/full-candidate ratios isolate the runtime correction;
audio-only ratios additionally change the explicit host subscription and must
not be attributed to this fix. Timings use serial alternating/rotating runs
after the complete test process has exited, with one discarded warmup for each
case and variant. They are coupled Node execution measurements, not exclusive
subsystem costs or browser real-time guarantees.

This closes an output-buffer correctness gap within stage5, not a new main
checklist item. The overall plan remains21/30 complete with nine open. No
physical-chip measurement is added; hardware acceptance, TOP=0, debugWIRE,
performance/cache work and the default-engine gate remain open. External
programming remains outside the requested scope.
