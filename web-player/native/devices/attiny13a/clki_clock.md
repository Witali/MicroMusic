# ATtiny13A logical CLKI divider

`clki_clock.c/.h` implement the explicit digital waveform fixture consumed by
the board owner. It is standalone and allocation-free, with no host imports,
timestamp, frequency prediction, event queue or CPU ownership. Source queue,
PB3 voltage resolution, total source-edge counts, startup/wake counters and
resumable CPU integration remain with their respective owners. This component
supports the full stopped-clock design; it imposes no period-only restriction.

The official reference is Microchip [DS40002307A sections6.3..6.4.2, printed
pages32..35](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=32).
CLKPR covers powers of two1..256 and affects synchronous clocks. Section6.3.1
specifies a glitch-free switch, two active edges, and a T1+T2..T1+2T2 interval;
the hidden ripple phase cannot be predicted. It does not establish this
module's particular initial phase or edge mapping as a silicon measurement.

## Selected deterministic policy

Initialization seeds counter0. Division by one starts at the supplied source
level; all other divisors start with output0. Initialization reports success
without delivering a transition. State fields are public for observation and
read-only to callers. `source_counter` is a bounded phase residue, not an
absolute count that could wrap after a long simulation.

Each `edge` call supplies a real alternating source level. While running,
division by one follows that transition if the new level differs from the
current output. Larger divisors toggle output every D/2 **rising** source
edges; falling source edges do not consume their phase residue. The module
uses the actual arrival sequence and never invents a midpoint for unequal
source high/low durations.

With `running=0`, an arriving edge changes only `input_level`. Output, phase
residue and any pending divisor stay frozen. Merely stopping or resuming the
main clock causes no edge: after resumption, the owner feeds later real source
transitions. No call is necessary during a hold, however long it lasts.

`request_divisor` keeps the old waveform until its next actual **system rising
transition**. At that transition the pending divisor becomes active, output
remains high, and its phase residue becomes0. No extra transition is delivered.
The last valid request replaces any previous pending request; a request for
the current divisor follows exactly the same rule. Invalid requests are
nonmutating and do not cancel an existing valid request.

When firmware writes at a CPU retirement rising edge, the selected policy
keeps one old period followed by one new period to establish the two active
edges: the explicit T1+T2 lower-bound fixture. It does not claim that variable
source timestamps or arbitrary debug writes have fixed wall latency. Debug
requests made at other phases use the named next-old-rise rule. A hold or gated
source can leave that request pending indefinitely without extrapolation.

`reset_divisor` preserves both current input and output, installs the requested
divisor, seeds counter0 and clears any pending request. No output edge is
fabricated. If D1 now has input!=output, the next input transition already
equal to the output is ignored; a later opposite transition is delivered.
The board chooses when this configuration reset is needed and separately
owns CPU/reset/domain state.

`edge` returns1 **only** for an actual output transition, writing its new level
to the caller's output byte. Return0 leaves that byte unchanged, though input
and phase state can advance. Invalid calls return a negative status and change
neither state nor output. The output byte must not overlap the state object.
Init/request/reset return1 for success and do not represent output events.

The independent optional [ideal-signal validator](clki_validation.md) checks
source period/pulse bounds and the selected conservative 2% rule. This divider
itself promises only the specified digital transitions. Analog thresholds,
slew reconstruction and measured hot-stop/restart behavior remain outside this
fixture. The [board integration](clki_board.md) owns validation and scheduling.
There are no external programming operations.

Run:

```text
node --test web-player/tests/attiny13a-clki-clock.test.mjs
```

The C/WASM tests compile with strict warnings and check for no host imports.
They cover all divisors and81 divisor pairs, gating/resume, reset mismatches,
request replacement, atomic invalid calls and edge delivery composed with the
separate queue at large uint64 timestamps.
