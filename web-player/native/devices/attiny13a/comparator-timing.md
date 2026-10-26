# Independent physical comparator timing

ATtiny13A only. The optional profile separates elapsed analog propagation and
reference startup from the comparator's clocked two-stage synchronization.
It is implemented in the native C/WASM device, with no instruction/edge callback
to JavaScript. Other device models require their own integration.

The authority is [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
section 13.2.2 (page 86) and Table 18-7 (page 127): analog propagation is expressed
in nanoseconds, while digital synchronization takes 1–2 CLK. The analog figures
depend on supply and input step conditions; a single typical value cannot serve
as universal chip calibration. The pinned PDF is registered in
[`tools/downloads.json`](../../../../tools/downloads.json).

## Select the profile

```js
const options = {
  resumable: true,
  oscillatorHz: 10000000,
  osccalHz: Array(128).fill(10000000), // Explicit flat fixture, not a measured RC curve.
  fuseLow: 0x72,
  comparatorTimingProfile: {
    domain: 'physical-ns-v1',
    propagationNs: 200,             // Synthetic example; caller supplies the value.
    bandgapStartupNs: 0,             // Explicit ideal/stable-reference fixture.
  },
};
```

Both delays are mandatory uint32 integers, including zero for an ideal response.
The profile requires resumable physical execution, selected by an OSCCAL table
or external `clkiProfile`. Nonzero legacy `comparatorPropagationHalf` or
`bandgapStartupHalf` cannot be combined with it. A null profile retains the
existing clock-counted fixture and its packages. No default physical delay is
invented, and the site's simplified engine selection is unchanged.

Package v6 preserves the profile, cache normalization includes it, and loaders
validate the native configuration export's exact signature. Missing capability
is rejected before guest reset/execution. Readers retain versions 1–5, which
cannot contain the later field, even when its value is null.

## Two domains and event order

The comparator's raw propagation/startup deadlines are uint64 picoseconds.
They use the board's physical timeline and do not stop when CLKI holds or scale
when CLKPR changes. A raw completion cannot itself publish ACO/ACI or trigger
ADC. Those effects require the actual enabled rising clock phases.

At a timed analog completion, the scheduler first brings digital state up to
the pre-edge anchor, then completes raw analog work, then delivers a coincident
rising edge. This is an explicit deterministic boundary convention, not an
analog setup/hold or metastability claim. At 9 MHz, a rational edge is rounded
up to an integer ps and can retain a nonzero phase residue. The scheduler tests
that residue against one ps of source progress, so this tie is still recognized.
An ordinary input injected at the edge timestamp follows that clock event.

For CLKI, a second analog settle occurs after pre-edge VCC/RESET/PB3 updates and
before source-edge delivery. Initial-low or divided-clock alignment can deliver
its first rising edge at half epoch zero; an explicit once-only arming hook lets
the normal ADC/comparator service sample that real edge without changing counters.
Repeated same-time service cannot reuse it. RESET cancels pending comparison,
reapplies the selected profile at the current physical timestamp, and retains
the existing clock/startup gates.

The native admission API is `device_configure_comparator(field,value)` before
init: field 1 propagation ns, field 2 reference startup ns, then field 0 enable.
Init rejects incomplete, mixed-unit or nonphysical configurations before touching
caller memories. Module faults for reversed time and deadline/sentinel overflow
are sticky until reset. The optional profile adds no memory growth or host import.

## Checks and limits

```text
node --test web-player/tests/*comparator*.test.mjs
node web-player/scripts/verify-comparator-timing.mjs
```

Checks cover both clock sources, retained clock-counted behavior, exact/adjacent
ps boundaries, quantized 9 MHz edges, CLKPR transitions, initially high/low holds,
PB3/ACME, first alignment, ADC triggers, RESET, package/cache restoration,
historical runtimes, invalid native admission and overflow. See the
[integration evidence](../../../reports/comparator-physical-20261026.md).

Delay values remain explicit profile inputs. Shared ADC/BOD reference enable
retention is not inferred from the local comparator delay. The separately
selected [shared reference profile](shared-reference.md) connects those owners
and requires zero local startup. Without it, callers that establish a stable
reference use zero startup as documented by the standalone module. Input offset, noise,
hysteresis, voltage-dependent trajectories and silicon measurements remain
outside this digital timing fixture. No official simulator has been executed.
