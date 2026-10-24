# ATtiny13A pin observation and native PCM

The board's live GPIO state, external trace history and native audio history
have separate responsibilities. Disabling an observer suppresses its stored
history; it does not disable GPIO, Timer0, ADC/comparator routing, PINB
synchronization, interrupt requests, wakeups or any required source-clock edge.
Those dependencies follow the [Microchip ATtiny13A data sheet, DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
especially sections9–14. Observer ownership is a host API contract, not a new
silicon behavior. Manufacturer register definitions remain unchanged.

## Independent bounded histories

The allocation-free board has two1024-record rings, each using the existing
16-byte pin record and integer timestamp. In the legacy clock contract the
timestamp is a half oscillator period; in physical mode it is a picosecond.

- The host ring stores selected changes to levels, driven, pullups, floating
  and contention masks. `device_pin_events[_ps]`, consume/clear and
  `drainPins[Ps]()` refer only to this ring.
- The private PCM ring stores level changes on PB1 for mono, or PB0/PB1 for
  stereo. The native integrator consumes it without JavaScript callbacks.
  Host draining or clearing cannot remove these events.
- The unmasked live pin snapshot is updated even when neither ring selects a
  change. A retained timestamp coalesces to its final full snapshot, including
  unselected changes at that same timestamp. Later unselected changes neither
  create a row nor rewrite an older row.

Cold initialization selects host mask63, legacy audio discard, and no PCM
subscription. MCU reset preserves subscriptions, histories and physical time;
the actual reset-induced pin changes are recorded normally. Starting a new
audio timeline clears only the private PCM backlog and takes its initial level
from the current live snapshot, never from stale host history.

The PCM subscription persists between capture batches and MCU resets. Its
bounded backlog must therefore be consumed by subsequent capture calls even
when host history is being drained independently. Restarting the audio timeline
discards that backlog; ordinary `audio_end` only ends active collection.

Each ring reports overflow as fault9/detail1024 rather than inventing missing
history. The existing public dropped counter belongs to the host ring; private
PCM drops have their own counter. Fault code/detail retain first-fault behavior.

## Host subscription API

`core.pinObservation` returns `{supported, mask, retainDuringAudio}`. It is a
separate getter; hardware `state()` retains its existing shape.

`core.observePins(mask, {retainDuringAudio:true})` accepts integer mask0..63.
The default options retain explicitly observed history during audio. The method
returns the current hardware state plus `pinObservation` as the new observer's
baseline. It preserves queued rows and creates no synthetic transition or
historical data for previously unobserved pins.

Examples:

```js
core.observePins(0, {retainDuringAudio:false}); // Native audio, no new host rows.
const baseline = core.observePins(1 << 2);     // Observe PB2 metadata and levels.
const events = core.drainPinsPs();            // Drain only this host's history.
```

The cold default is `{supported:true, mask:63, retainDuringAudio:false}` to
preserve the former complete trace and automatic audio discard contract.
With retain false, audio collection removes host rows through its collected
frontier; it never removes future rows. With retain true, the host must drain
boundedly itself. Mask changes preserve all already-queued history.

Device/package renderers preserve the core's observation policy, including an
explicitly retained observer. Audio-only callers can request mask0 themselves;
the speed benefit of suppressing host history is workload-dependent.

The two optional native exports are `avr_device_pin_trace_config(mask,retain)`
and `avr_device_pin_trace_configuration()`; the latter packs mask|(retain<<8).
Invalid arguments return0 without changing board state. The JS API additionally
validates option types and unknown keys. Original package v1/v3 runtimes expose
`supported:false` and preserve their legacy behavior; an explicit observer
request fails rather than pretending independent history is available. No
package-format or generated CPU import/continuation ABI change is required.

## Collection and pressure

Sample begin and sample completion always collect. Ordinary clock calls retain
eager collection after each barrier. Resumable phases collect at queue pressure
for at most128 requested halves and also whenever a native clock span yields
BUFFER_READY. Halted waits retain their existing bounded advancement; resumable
waits collect on pressure and ordinary waits remain eager. CPU scheduling and clock calls,
fault time accounting, latched remaining work and reset priority are unchanged.

Pressure uses total occupancy, including a wrapped queue, with a512-row
watermark in either the private PCM ring or legacy audio-owned host history.
Explicitly retained host history is excluded: the native collector cannot free
it, so treating it as BUFFER_READY would create an undrainable retry loop. Its
capacity limit still faults honestly if the host fails to drain it.

Exceptional long resumable spans collect before advancing to restore headroom
consumed by deferred short phases, and collect after advancing. Internal-source
requests longer than128 halves use a separate event loop that yields at the
512-row watermark. It settles all events at the current timestamp before
yielding; fault/reset, request completion and wall-deadline ties retain their
original priority. The native bridge consumes the records and retries only the
remaining half periods, without replaying instruction effects or calling JS.
An already-full watermark can yield with zero consumed halves.

The ordinary event loop and short internal-source spans retain their previous
path. CLKI can also yield within a CPU half when many source transitions fill
the queue. Every source transition and peripheral event keeps its original
timestamp. Ordinary fault accounting still charges to the original requested
endpoint; asynchronous reset stops at its event. This does not add a general
continuation or unbounded-history guarantee for nonresumable command stalls.

Integration uses integer accumulated high time and the existing rational audio
grid. Deferring addition across a constant level does not change the integral.
Future events beyond the current audio endpoint remain queued for later samples.
The production module retains fixed two-page memory and no host imports; the
additional ring fits inside that existing memory limit.

## Verification and measurement

`device-pin-observation.test.mjs` checks the former default ring algorithm,
same-time snapshots, wrap/overflow prefixes, ownership, subscriptions and full
private board-state equality with active CLKI/ADC3/Timer/GPIO/IRQ consumers.
`attiny13a-pin-observation-runtime.test.mjs` covers the public API, independent
host drains, channel/rate boundaries, reset/sleep and original package runtimes.

`attiny13a-audio-pressure-runtime.test.mjs` compiles the unchanged current board
and bridge with only its public pressure query forced true. This eager policy
is the oracle for deferred collection; it does not duplicate MCU instruction
semantics. Checks compare exact PCM, full public/private CPU state, memories,
IRQ frames and Flash generation through pressure/wrap, sample ties, stalls,
SPM, resets and held/partial CLKI phases. Both builds have fixed two-page memory
and no host imports. Performance is measured separately, without this override
or counters, using `scripts/benchmark-pin-observation.mjs`.

`attiny13a-long-audio-span.test.mjs` independently integrates the full host
trace in short physical-time slices, without a native audio subscription. It
compares exact PCM and complete CPU/memory/device observations across long SPM
phases, low sample rates and a fractional sample grid at9/9.6/20MHz. The existing
eager-collection reference alone cannot detect an overflow inside one long
native advance. `device-internal-buffered-span.test.mjs` checks the actual board
API against the unbuffered path, including endpoint/reset ties, fractional
phase, wrap, CLKPR, zero-progress yields and ordinary-fault time accounting.
