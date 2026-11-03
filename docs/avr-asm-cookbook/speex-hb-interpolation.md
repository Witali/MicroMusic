# Finite HB1 interpolation: share endpoint loops before using more assembly

This is an **isolated measured candidate**, not an integrated decoder change
or a real-time admission. Target: ATmega328P/classic AVR5, GNU AVR ABI,
AVR GCC 7.3.0, `-Os -flto -fwrapv -fno-strict-aliasing -mcall-prologues
-mrelax`, avr8js 0.21.1. The probes are portable C arithmetic. The ordinary
C implementation remains an explicit baseline; no architecture or ASM
selection policy changes. No working-memory buffer is added by the candidate.

The interpolation and sequential margin algorithm originate in Xiph Speex
1.2.1, with BSD provenance in
`Codecs/Speex/AVR/vendor/speex-1.2.1/COPYING`. The finite-domain proof,
loop sharing and probe implementation are original project work.

## Use the actual domain before narrowing arithmetic

The pinned HB1 codebooks have 64 by 64 endpoint vectors. Every component is
a positive multiple of sixteen, with these exact minima and maxima:

```text
(2704,9024) (4800,11168) (6880,15088) (8880,17936)
(12272,20560) (13856,22784) (17328,24256) (19760,25600)
```

Therefore every old/new component difference fits signed16: its maximum
magnitude is 9056. The two separately rounded Xiph P14 products are integral
in this domain. The quarter-one expression can use one difference shift:

```c
first + ((second - first) >> 2)
```

For quarter three, exchange `first` and `second` and reuse the same loop.
Divisibility by sixteen makes the negative difference shift exact as well.
Hoist the quarter selection outside the eight-component loop. Keep a separate
half-step loop and a final-endpoint copy. No multiplication, division, state
cache or new assembly routine is needed.

This difference form requires the proven component domain. General signed16
endpoints can overflow `second-first`; arbitrary nonmultiples of sixteen can
round differently. Retain the original formulation for a general interface.

## Preserve sequential margin semantics

The lower/upper repairs depend on earlier repaired components. Checking the
original adjacent gaps alone is insufficient. The last endpoint clamp is
necessary: 25600 exceeds 25736-410.

An exhaustive check of all 4096 squared endpoint pairs at four quarters
(67,108,864 vectors) proves only three checks redundant here:

- The first endpoint is always at least 2704, so its lower clamp cannot fire.
- The upper repair of component index 3 has minimum sequential slack 38.
- The lower repair of component index 4 has minimum sequential slack 38.

All other repair branches occur. Preserve the two separate half shifts in
the upper repair; a combined average can change rounding after a prior repair.

Removing checks through `if (i != position)` inside the loop was slower and
larger than the ordinary margin loop in the isolated probe. Explicitly listing
the remaining ten repairs removes that loop overhead, at a Flash cost.

## Isolated measurements

Retained evidence: [finite-domain proof](../../Codecs/Speex/AVR/reports/wb-interpolation-domain.json)
and [seven AVR recipes](../../Codecs/Speex/AVR/reports/wb-interpolation-unit.json).

The workload contains 17,044 valid correlated endpoint/quarter vectors per
recipe: every old and new endpoint, all four quarters, equal endpoints and
component-extreme endpoint pairs. Output pointers exercise all 256 low-address
bytes. Function timing includes its final RET and compiler prologue/epilogue,
excluding the mailbox. All recipes use the same build flags and vector order.

| Recipe | Mean cycles/call | Whole probe Flash | Own stack |
| --- | ---: | ---: | ---: |
| Original loop with per-component switch | 646.080 | 470 B | 7 B |
| Difference form, per-component switch | 618.067 | 454 B | 7 B |
| Hoisted switch, separate quarter loops | 469.061 | 514 B | 4 B |
| Hoisted switch, finite checks inside margin loop | 493.076 | 526 B | 4 B |
| Hoisted switch, explicit finite repairs | 365.061 | 694 B | 4 B |
| Shared quarter loop, ordinary margin | 467.311 | 476 B | 4 B |
| Shared quarter loop, explicit finite repairs | 363.311 | 656 B | 4 B |

Shared quarter loops with ordinary margins improve every measured call by
108..229 cycles, averaging 178.769 cycles, for six additional probe bytes.
Adding explicit finite repairs improves every call by 212..333 cycles against
the original, averaging 282.769 cycles, for 186 additional probe bytes. The
difference-only recipe regresses some calls by fourteen cycles; fewer source
operations alone do not establish the preferred implementation.

These are isolated image sizes, not final firmware deltas. Repeated LPC frames
can bypass interpolation, and the complete decoder has other work. Do not
multiply these figures into a claimed whole-corpus speedup without measuring
the integrated firmware. There are no active interrupts or physical-board
measurements in this probe.

Every one of the 119,308 measured calls matches an independent host model of
the separately rounded P14 interpolation and original sequential margin.
Read-only endpoints, output bounds, guards, callee-saved registers, r1 and
return stack depth are checked. Only isolated C interpolation functions run;
the full Speex C decoder is never executed or timed.

## Reproduce

```sh
python Codecs/Speex/AVR/tests/check_wb_interpolation.py
# Optional complete vector-domain proof; requires an existing NumPy install.
python Codecs/Speex/AVR/tests/check_wb_interpolation.py --exhaustive-margin
python Codecs/Speex/AVR/tests/build_wb_interpolation.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_wb_interpolation.mjs Codecs/Speex/AVR/build/wb-interpolation-unit
```

`--numpy-path` accepts an existing local dependency directory if NumPy is not
on the default Python path. Build metadata binds normalized source hashes,
compiler/options and exact binary hashes; the verifier rechecks those hashes.
Ignored `build/wb-interpolation-unit/verification.json` contains per-quarter
cycles, paired deltas, sizes and correctness results. Production integration
still needs full PCM/state/reset comparisons, final size/stack measurements,
and the production timer/queue workload with active IRQs and zero underruns.
