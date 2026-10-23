# Compact integer HQ4-T one-shot profiles

This research decoder adds an independent output state to the original signed
eight-stage HQ4 lattice. After storing the unfiltered lattice state, it computes
`y = s8(x + previous - (previous >> shift))`. The output state starts at zero;
it never changes lattice state, pitch or frame timing. At EOF the ordinary
one-shot path emits midpoint silence directly.

The source defaults to shift 2. `tools/probe-hq4-natural-timbre.py` generates a
profile-specific source/address and uses the existing isolated HQ4 builder's
assembly and independent three-engine verification transport. The numerical
callback is the exact matching integer tilt model. No existing source file is
modified by that adapter.

| Shift | Previous-sample retention | Decoder bytes | Maximum stream bytes |
|---|---:|---:|---:|
| 1 | 1/2 | 418 | 605 |
| 2 | 3/4 | 420 | 603 |
| 3 | 7/8 | 422 | 601 |

The compact stage destructively subtracts the leaked part from its previous
state before adding it to the new output. That state is overwritten by the
result, so the extra temporary register/move of the earlier HQ4-T is unnecessary.
It uses register r11 and no additional SRAM. Profile 1 needs five one-cycle
instructions per spoken sample plus its startup clear.

Search compares gain multipliers .5/.75/1/1.25/1.5/2 and automatic rate-fitting
alternatives. A local minimum-cost spectral-half reuse method saves just the
bytes needed by the output filter. All candidates preserve every original
sample. Exact internal lattice wraps, signed -128 multiplication cases and
output-filter wraps cannot increase; clipping and large output steps are also
rejected. These checks do not establish naturalness.

See `../../research/natural-timbre/README.md` for retained models, results,
reproduction commands and the intelligibility/timbre tradeoff. Run
`python tools/test-hq4-natural-timbre.py` for exact T2 compatibility, explicit
overflow diagnostics and duration-preserving rate-fit tests.
