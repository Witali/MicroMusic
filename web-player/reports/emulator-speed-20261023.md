# Current emulator speed, 2026-10-23

The full device currently delivers about7.16million AVR instructions/second
on the arithmetic kernel in its compatible clock mode, and3.89million with
physical-time instruction continuation. The full CLKI waveform is more costly:
at20MHz,25ms of kernel/audio capture takes about410ms. Real firmware capture
with the compatible full-device engine runs at0.62–0.91times real time in these
three excerpts. The production JS audio filters contribute less than0.3ms per250ms.

These are serial Node measurements on this host, not browser guarantees. The
direct kernel and clock capture measure different workloads and clock modes.
They must not be treated as isolated CPU/peripheral timings.

## Runtime and retained evidence

Host: AMD Ryzen5 5600X,12 logical CPUs, Windows10.0.26300 x64,
Node22.22.3, V8 12.4.254.21-node.56. No CPU affinity, forced GC or host-load
control was applied. No other agent benchmark/test workload ran in parallel.

The measured implementation is `0792e97` on `codex/avr-to-wasm`.
The112340-byte device WASM has no host imports, fixed two-page memory and
SHA-256 `ae66ad2e64f8e96af046cd02b04f49c82c371026b8686bd54647678c8a8efa97`.
Both scripts checked every normalized source hash against the native build
manifest before timing. Report JSON preserves Git state, firmware/runtime/source
hashes, individual trials, min/max/median/mean/standard deviation and host data.
The new clock benchmark script was untracked during its run, with its exact
source hash retained in that report.

- [Kernel and clock raw results](emulator-speed-20261023-clock.json):147 timed
  runs across21 cases, seven trials per case, following untimed warmups.
- [Firmware/PWM/DSP raw results](emulator-speed-20261023-firmware.json):48 timed
  runs across three firmwares and four optimization configurations, four trials
  per configuration, with576 state checkpoints.

All program/register/cycle/phase/PCM assertions passed. The full regression
suite passed1128 tests at the preceding implementation checkpoint; this
measurement adds a benchmark and reports without changing emulator behavior.

## Direct instruction throughput

The source-only program initializes two registers, then repeatedly executes
`ADD; EOR; INC; RJMP`. Four loop instructions require five emulated CPU cycles.
Each fresh instance executes exactly1000000 retired instructions through one
public `run(N)` call, requiring1249999 CPU cycles. Construction, compilation,
hashing and assertions are outside the timer. Idle skipping is disabled.
The final registers, PC, SP, flags and cycles agree across all three cases.

| Engine | Median ms | Observed min–max ms | Million AVR instructions/s | Million emulated CPU cycles/s |
| --- | ---: | ---: | ---: | ---: |
| Translated CPU, historical limited peripheral model | 14.91 | 14.31–15.72 | 67.07 | 83.84 |
| Full ATtiny13A, compatible fixed-source clock | 139.73 | 138.88–151.78 | 7.16 | 8.95 |
| Full ATtiny13A, physical source and resumable CPU | 257.26 | 256.31–268.33 | 3.89 | 4.86 |

The historical model is a throughput reference with less hardware coverage,
not an equivalent substitute for the full device. All three run translated
AVR instructions as WASM. The physical continuation path retains phase state,
has observable flag/retirement boundaries and disables unproved instruction
blocks/idle skipping. The full-device timers also include the real scheduler
and interrupt checks even though the kernel enables no peripheral activity.

## Full external CLK and divider cost

Each case captures25ms at48kHz,1200 mono samples, on the same arithmetic kernel.
PB1 remains low, so every sample must equal-1. Both physical source modes use
the resumable CPU. The external source is a50%-duty waveform with exact integer
picosecond phases; optional electrical validation is disabled. GPIO CLK input
transitions, divider state and native pin/audio collection are active.

Both modes start at D1 and receive the same protected CLKPR request at time zero.
One old source cycle precedes the selected divisor. An independent count model
checks delivered phases, instruction retirements, PC and register results.
Internal and external source cases agree on full CPU/register/phase snapshots
for each frequency/divisor; per-case snapshots and PCM are deterministic across
trials. Each timed call excludes descriptor generation/submission and construction.

Values are seven-trial medians. Real-time factor is25ms divided by measured
capture time: above1 means faster than the represented interval.

| Source MHz | Divider | Internal source ms | Full CLKI ms | CLKI real-time factor |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 6.72 | 20.48 | 1.221× |
| 1 | 8 | 1.13 | 16.04 | 1.559× |
| 1 | 256 | 0.33 | 14.77 | 1.692× |
| 10 | 1 | 67.53 | 214.75 | 0.116× |
| 10 | 8 | 8.53 | 165.24 | 0.151× |
| 10 | 256 | 0.68 | 146.26 | 0.171× |
| 20 | 1 | 130.40 | 410.29 | 0.061× |
| 20 | 8 | 16.90 | 314.24 | 0.080× |
| 20 | 256 | 0.84 | 292.97 | 0.085× |

For20MHz/D1 the observed capture range was403.92–492.30ms; at D256 it was
288.36–316.45ms. The sub-millisecond internal-source cases have substantial
relative timer/allocation variability, so their large headroom values should
not be read as stable playback guarantees.

At20MHz all divisors consume the same1000000 source transitions. D256 retires
only1564 instructions versus400001 at D1, yet still takes293ms. This strongly
suggests source-edge scheduling/pin work dominates that external-clock workload;
it is an inference from scaling, not an exclusive-time profile. The current
periodic descriptor eliminates per-edge JavaScript input/refill work, but the
native runtime still services every supplied transition. Merely avoiding JS
callbacks does not eliminate that work.

## Real firmware, PWM and audio filtering

`benchmark-device.mjs` measures250ms at48kHz per fresh device. It uses the
compatible fixed-source full-device clock, with no CLKI stream, calibration
table or resumable backend. The baseline has `fastIdle:true,optimizeFlags:true`.
Each firmware also ran the other three flag/idle configurations in balanced
order. Raw and filtered Float32 PCM, full registers/I/O/SRAM/Flash/EEPROM and
selected architecture/IRQ diagnostics agree at every1024-frame block endpoint
and across trials. This checks the selected observations, not every hidden latch.

Capture includes translated CPU, native peripheral scheduling, pin integration,
wrapper allocation/copy and initial capture configuration. DSP is separately
timed production `Renderer.processRaw`:35Hz high-pass,9kHz low-pass, gain0.65.
Construction, snapshots and validation are outside both timers.

| Firmware | Capture median ms | Observed min–max ms | JS DSP median ms | Capture + DSP real-time factor |
| --- | ---: | ---: | ---: | ---: |
| rhythmic | 274.91 | 272.88–279.30 | 0.153 | 0.909× |
| lumiere-stereo | 280.22 | 274.30–309.13 | 0.265 | 0.891× |
| hq4-chego-auto | 403.60 | 397.55–405.94 | 0.176 | 0.619× |

Library-cache-bypassed construction medians were25.80–29.20ms; verified
translation-cache hits into fresh device memory took1.24–1.31ms. Cold refers
to bypassing the application cache, not a new process or a forced V8 cache miss.
All retained channels contained finite, changing samples. These are initial
excerpts, not complete compositions or browser AudioWorklet callback timings.

## Implication and reproduction

The measured bottleneck warrants further native clock/scheduler work. A future
periodic-source optimization can compute irrelevant intervals arithmetically
while retaining divider residues and stopping at every observable GPIO/ADC/
timer/CPU/reset boundary. This benchmark does not implement or claim that gain.
Exclusive subsystem profiling and the default-engine performance gate stay open
in [the plan](../native/ATTINY13A_PLAN.md).

Run serially from the worktree root:

```powershell
node web-player/scripts/benchmark-device.mjs --frames 12000 --rate 48000 --trials 4 --out build/benchmarks/device-current-20261023.json
node web-player/scripts/benchmark-clock.mjs --instructions 1000000 --frames 1200 --trials 7 --out build/benchmarks/clock-current-20261023.json
```

Inputs and times for every measured run are retained in the linked JSON files;
no MIDI source or raw audio files were created for these measurements.
