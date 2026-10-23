# Finite CLKI periodic producer

This optional producer compactly describes the same exact logical transitions
as raw queue entries. It is not an inferred frequency or an endless oscillator.
The caller explicitly supplies a start time, initial level, positive high/low
durations, finite edge count and inclusive known-input horizon. Timestamps are
uint64 picoseconds; MAX is reserved as the exhausted next-edge sentinel.

First transition is `start + (initialLevel ? highPs : lowPs)`, with the opposite
level. Further transitions alternate after the duration of their newly current
level. There is no 50% duty requirement and no Hz rounding. The final actual
transition is checked before initialization succeeds:

```text
final = start + floor(count/2)*high + floor(count/2)*low
              + (count odd ? (initialLevel ? high : low) :0)
```

Checked split products avoid overflowing `high+low`, including when count0/1
does not need that sum at all. Final timestamp must be below MAX and at/before
the horizon. Every actual timestamp therefore fits before the state is accepted.
Unused duration beyond the last edge is never calculated. For example, a
one-edge producer can use a huge duration for the level reached by its last
edge; that unused duration does not create a second transition.

Count0 is an explicit known hold: initial/current level stays unchanged,
`peek` and `consume` return EMPTY, next time is MAX, and the finite horizon is
still available. Exhaustion never extrapolates another edge, even if the known
horizon extends far beyond the last transition. New input requires an explicit
new producer or raw edge batch governed by the board's global input contract.

State is caller-owned and allocation-free, with public read-only fields.
Init/peek/consume return1 for success,0 for exhaustion, or a negative status.
Peek writes output only on success, and never changes producer state. Consume
updates current/next level and remaining count once. All rejected operations
leave state/output unchanged. Output overlapping any producer state is rejected.
There are no host imports or per-edge JavaScript callbacks.

The **board owner** checks start/global horizon/queued-tail continuity, merges
the producer's exact transitions with its other inputs, resolves physical PB3,
validates the waveform, and delivers source events to its divider and CPU.
It can fill a small bounded queue lazily in C while consuming a much longer
finite producer. Queue backpressure must not consume the unaccepted producer
edge. The global horizon describes the entire producer; the queue's own horizon
need cover only generated entries until the final global hold is published.
Those board integration rules are not implemented inside this producer.

This remains a logical fixture: it does not assert electrical validity, silicon
phase, or safe hot frequency changes. The separate optional validator handles
the explicitly selected electrical profile. Raw irregular transitions and true
clock holds remain supported by their own queue; this compact input adds no
period-only restriction to the full CLKI contract.

Run `node --test web-player/tests/attiny13a-clki-periodic.test.mjs`.
