# ATtiny13A logical CLKI stream

Implemented here: a standalone, allocation-free timestamped input queue.
The [device owner](clki_board.md) connects it to PB3, the source divider,
startup/wake source-CK counters and the resumable translated CPU. This component
contains no board or CPU policy and does not impose a period-only restriction.
It has no host imports or per-edge callbacks.

The caller supplies disjoint state and edge storage with a fixed capacity.
Initialization supplies an explicit uint64 picosecond time and logical level;
it emits no transition. `UINT64_MAX` is reserved throughout. Edge times are
strictly increasing and levels alternate. No Hz, duty cycle or guessed next
edge is stored. Both high and low holds can last arbitrarily long within the
representable timeline.

`attiny13a_clki_enqueue` validates an entire batch and publishes its inclusive
known-input horizon atomically. Every new transition must be strictly later
than the previously published horizon; no insertion at that boundary or into
its already described past is accepted. The new horizon cannot move backward
and must cover the whole batch. A zero-length batch with NULL input explicitly
publishes a longer interval with no new transitions. Republishing the same
horizon is harmless. This also works while the queue is full.

An empty queue alone means **no queued edge**, not a known clock hold beyond
the horizon. `hold_until` returns `UNKNOWN_HORIZON` if the producer has not
described the requested endpoint. Within the horizon it moves the cursor only
when no edge is due at or before the endpoint. An exact edge boundary requires
`consume`, not a hold. Holding advances wall cursor time and preserves the
logical level; it never manufactures a clock phase.

`peek` does not change state. `consume` moves the cursor and current level to
the next edge. The board owner must first merge that timestamp with its other
scheduled domains and apply the real PB3 transition in its declared event
order. No CPU phase, GPIO synchronizer or peripheral advances inside this
module. An optional NULL consume output supports peek-then-discard.
The external stream remains owned by its producer across a guest CPU Reset;
the board must not reinitialize this queue merely because the CPU resets.
Explicit init starts a new stream and discards prior queue metadata.

All rejected calls preserve metadata, ring bytes and outputs. Backpressure
accepts no partial batch and publishes no horizon. Invalid time/level/argument
statuses are nonsticky; the caller can correct the batch and retry. Input and
output arrays that overlap queue metadata/storage are rejected. The owner
serializes calls; this is not a concurrent producer/consumer primitive.

The ring wraps without changing event order. Producer batches can be partitioned
arbitrarily as long as each intermediate horizon ends before the next not-yet-
submitted edge. Once a horizon promises a hold, the producer cannot revise it.
After consumption through that horizon, resume by submitting a later opposite
edge and a new horizon. A capacity-limited owner drains before retrying the
same rejected batch.

Example: init at0 low; publish `(10,high),(25,low)` with horizon40. A hold to9
is valid; a hold to10 returns `EDGE_PENDING`. Consume10, hold to24, consume25,
then hold to40. A hold to41 returns `UNKNOWN_HORIZON`. Publishing `(50,high)`
with horizon60 resumes the clock without inventing transitions in40..50.

This queue is an **ideal logical fixture**. The separate optional
[validator](clki_validation.md) checks the selected ideal-signal bounds; the
queue itself establishes no electrical guarantee for arbitrary supplied pulses,
slew, stops/restarts or cycle-to-cycle changes. It does not choose an initial
divider phase or a CLKI-to-system-clock latency. Physical measurements and
analog threshold reconstruction remain open. The authoritative
electrical reference remains Microchip [DS40002307A sections6.2.1/6.3.1 and
Table18-3](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=125).
There are no external programming protocol operations in this component.

Run the standalone C/WASM tests with:

```text
node --test web-player/tests/attiny13a-clki-input.test.mjs
```

The existing test compiler uses a read-only Emscripten SDK, generates artifacts
under ignored `build/analog-tests`, enables strict compiler warnings and rejects
all host imports.
