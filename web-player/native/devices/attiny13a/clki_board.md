# ATtiny13A external clock integration

The optional `clkiProfile` connects an actual timestamped CLKI source to PB3,
CKDIV8/CLKPR, the device scheduler and the translated CPU/IRQ continuation.
CKSEL must be00 and the generated CPU must use `resumable:true`. The source
does not require a calibration curve for the inactive internal RC oscillator.
Its absolute timeline is integer uint64 picoseconds; no frequency is inferred
from the last two edges or used to manufacture missing transitions.

The normal internal-clock engine is unchanged. This source model runs a supplied
firmware image; ISP/HVSP and external-chip programming remain outside scope.

## Source, level and phase

`lib/attiny13a-runtime.js` accepts:

```js
const core = new ATtiny13A(flash, eeprom, {
  fuseLow: 0x70,       // CKSEL00, CKDIV8 unprogrammed, SUT00
  resumable: true,
  clkiProfile: {
    phasePolicy: 'digital-noninverting-zero-seed-v1',
    initialLevel: 1,
    electricalValidation: 'none',
  },
});

// A finite 20MHz source with equal25ns phases, followed by a held-high interval.
core.injectClkiPeriodicPs({
  startPs: 0n, initialLevel: 1, highPs: 25000n, lowPs: 25000n,
  transitionCount: 80000n, knownUntilPs: 3000000000n,
});
const pcm = core.capturePhysical(16, 8000, 2); // Completes at2ms.
core.runUntilPs(3000000000n);                 // Clock remains held until3ms.

// Resume with precisely described phases. No transition is invented at3ms.
core.injectClkiPeriodicPs({
  startPs: 3000000000n, initialLevel: 1, highPs: 25000n, lowPs: 25000n,
  transitionCount: 4000n, knownUntilPs: 3100000000n,
});
```

Check the boolean admission result before using a segment: `false` means
backpressure, with no partial segment/horizon accepted. Invalid arguments throw.
The same source also accepts arbitrary alternating `{timePs, level}` records
through `injectClkiPs({edges, knownUntilPs})`. Unequal high/low durations, an
odd number of transitions and stops at either level are supported.

A known-input horizon is inclusive: all transitions through that time have
already been described. An edge-free interval holds the last level. A bounded
run beyond the horizon returns `WAIT_INPUT` there; a known held interval returns
`WAIT_CLOCK` at its requested observation point. Neither is a reset or fault.
Extending a hold never inserts transitions into the already published past.

The phase fixture starts D1 with output=input, and D>1 with output low and a
zero divider counter. Initial high at D1 admits work at time zero without
charging an invented edge; initial low waits for a real rising phase. D1 follows
the actual unequal source phases. Larger divisors toggle on every D/2 eligible
source rising edges. MAIN gating freezes the divided output, counter and pending
switch, while raw CLKI/PB3 and independent wall time can continue.

A CLKPR write retains the old divider until its next actual system rising edge,
then installs the new divisor with output high and counter zero. This is the
named deterministic fixture documented in `clki_clock.md`, not a measured
silicon ripple phase. Source holds cannot finish the pending transition.

GPIO receives explicit falling/rising system transitions. ADC and Timer0 advance
only through delivered clock phases in their enabled domains. Their existing
sampling, prescaler and event logic remains responsible for the phase at which
each effect becomes visible. Source level and divider residue are retained;
stopping and resuming does not restart a partially completed instruction.

## Event ordering, reset and independent time

`clki_board.inc` belongs to this device and is included by `peripherals/device.c`.
It joins the source queue with the existing GPIO, analog, VCC, power, NVM and
watchdog deadlines. At a timestamp, recognized RESET/supply changes and async
reset sources precede source delivery. An eligible source transition updates
PB3, the divider, GPIO sampling, ADC and Timer0. Ordinary equal-time GPIO/analog
injections retain the documented after-sampling convention.

The translated CPU suspends at an existing bus/clock barrier. It retains latched
addresses, operands, read results, stage and remaining phases in native linear
memory. Completion commits the next eligible effect once; reset cancels the
remaining effects and preserves SRAM writes completed at earlier phases.
Native interrupt entry similarly retains its staged stack writes and vector.

Source CK, system wake cycles and wall time are separate quantities:

- Fuse startup waits for its independent SUT watchdog timeout, then20 actual
  source CK (6 startup plus14 reset CK). A release/arm-timestamp rise is excluded.
- The watchdog reset pulse needs one subsequent raw source CK to end, including
  when MAIN is gated. An absent clock cannot discharge it by elapsed wall time.
- Power-down wake needs its selected source startup and independent BOD recovery,
  then four actual system rises. The startup-completion rise is not reused as
  a wake-delay cycle. Idle/ADC sleep retain their existing domain gates.
- Watchdog oscillator ticks, POR/BOD/RESET qualification and EEPROM/Flash wall
  deadlines continue when CLKI is held. Source-dependent progress stays stopped.

Unbounded `step/run/clock/interrupt/runBlock` are rejected in this profile: use
`runUntilPs` or physical capture with a known input interval. Pending Flash
generation changes cannot replace an active instruction's latched continuation;
the old instruction/IRQ completes before recompilation and the next fetch.

## Queues and native output

`clki_input.c/.h` owns the512-slot input queue. The finite `clki_periodic.c/.h`
producer stores a descriptor and materializes more edges inside C/WASM as slots
become available. Its full declared horizon is separate from the materialized
queue horizon. This supports long source intervals without JavaScript refills;
the source never extends beyond its finite transition count. `periodicRemaining`
counts unmaterialized transitions, while `queued` counts materialized ones.

The current full-waveform profile services each supplied source transition.
Compact periodic input removes host traffic and the queue-size limit on a
descriptor; it does not yet skip source transitions with analytic fast-forward.
Such an optimization must preserve every observable phase, pin read and event.

Physical audio integrates PB0/PB1 in WASM. Long CPU waits and long individual
clock barriers yield internally when the pin ring reaches512 events, drain the
ring into the audio accumulator, then continue the same deadline/phase. There
is no per-edge JavaScript call. Buffer draining neither repeats instruction
effects nor allows an instruction to overrun its observation deadline.

Outside physical capture, callers retaining the full pin trace must consume
the finite1024-event output ring often enough. Overflow is an explicit fault;
CLKI transitions and pin events are never silently dropped.

## Qualification and software boundary

`electricalValidation:'datasheet-ideal-v1'` enables the independent validator.
It checks VCC-dependent period and pulse-width bounds, the conservative combined
2% frequency/period rule and its RESET comparison baseline. Ideal zero-slew
digital transitions are assumed. The board uses the worst observed supply tier
between transitions; this is a conservative fixture, not analog threshold
reconstruction. No universal receiver delay or analog oscillator settling curve
is invented. `none` leaves the explicitly described digital waveform unqualified.

CLKI owns the PB3 pad; separate GPIO/analog source injections on PB3 are rejected.
An attempted DDRB3 output faults explicitly because contention/alternate mux
behavior has not been measured. See `clki_validation.md` for signal assumptions,
`interfaces.md` for unresolved physical/debug boundaries, and `cpu_phase.md` for
the stable continuation ABI. Package v5 preserves and validates these selections.

## Verification

- `attiny13a-clki-board.test.mjs`: real C board clocks, GPIO sampling, Timer0/ADC
  holds, independent WDT/NVM, reset/startup/wake ties and domains.
- `attiny13a-clki-runtime.test.mjs`: all123 instruction forms with unequal phases,
  half-phase/1ps observations, stack/IRQ/reset cancellation, Flash recompilation,
  held-source audio, qualification and package round trips.
- `attiny13a-clki-periodic-runtime.test.mjs`: arbitrary/periodic equivalence,
  80000 transitions at20MHz, stereo output and partitions, source seams and holds,
  generated-edge qualification after refill, CLKPR at a512-edge refill boundary,
  CKDIV8 wake and exact timestamps above2^53.
  Regressions reproduce pin-ring overflow during Power-down, fuse startup and
  all three LPM forms at /256, then compare the fixed capture with internal-clock
  execution. Slow native IRQ stack phases are compared with that reference too.
- Standalone queue, divider, periodic producer, validator and host tests cover
  exact arithmetic, all nine divisors/81 switch pairs, atomicity and backpressure.

Sources: [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections6.2.1,6.3,7,8.2.4,10.2.4,14.5 and Table18-3; the pinned official
[device definitions](../../../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
Silicon timing measurements and analog receiver calibration remain separate
open plan items; this software integration does not claim to complete them.
