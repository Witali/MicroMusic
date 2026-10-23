# CLKI datasheet-ideal-v1 validation

This standalone optional validator observes real logical transitions; it never
generates a clock, modifies a divider or advances a CPU. State is caller-owned,
allocation-free, and timestamps are exact uint64 picoseconds with MAX reserved.
All three APIs return a reason bitmask, with zero meaning success/no violation.

Microchip [DS40002307A Table18-3, printed page125](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=125)
defines maximum4/10/20MHz, minimum periods250/100/50ns and high/low widths100/40/20ns
for VCC ranges starting at1.8/2.7/4.5V through5.5V. Those completed-interval limits
are checked inclusively at their voltage boundaries. Outside1.8..5.5V produces
an explicit VOLTAGE reason; no arbitrary tier is selected. The caller supplies
a qualified conservative VCC for each completed interval; point samples cannot
establish the unobserved supply trajectory between edges.

The declared fixture assumes ideal zero-slew logical edges. It does not measure
analog input crossings, rise/fall times, noise or metastability, and does not
certify a physical waveform from timestamps alone. Analog receiver qualification
and silicon phase validation remain open.

[Section6.2.1, page31](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=31)
speaks of2% frequency variation and Reset during larger changes, while Table18-3
names2% period changes. This profile conservatively requires **both** readings:
`abs(currentPeriod-previousPeriod) <= min(currentPeriod,previousPeriod)/50`.
Integer division floors the right side, exactly expressing the rational
inequality for integer ps. Subtraction and division avoid overflow near MAX.
Neither direction is silently given the more permissive denominator.

The initial level has no known preceding physical transition. Therefore the
first actual edge establishes width history without validating that partial
span; the first rise establishes period history. Later edges must strictly
alternate, increase physical timestamps and not precede the observation cursor.
`set_reset` may share a timestamp with an edge, so the board owner determines
the explicit equal-time Reset/edge ordering.

Effective Reset transitions clear the variation baseline while retaining actual
edge/rise history. While Reset is held, voltage, physical width and period limits
are still checked when defined. Variation is suppressed. After release, the
first rise establishes a new comparison origin; two complete post-reset periods
are required for the next comparison. A period spanning Reset is never used in
that comparison. Repeated same-state Reset observations do not clear baseline.

There is no maximum period and no periodic work. A long held level remains
valid until another observation; restarting with a changed period can report
VARIATION unless the Reset baseline was cleared. This is an optional diagnostic
profile and does not turn a stopped-clock digital fixture into a fabricated
silicon guarantee.

Electrical reasons record the current observation and new physical history,
and accumulate in `violations`. The returned mask describes only this edge.
Malformed time, level, initialization or arguments return MALFORMED **without
changing any state**, including sticky reasons. The owner can therefore reject
bad input atomically; after an electrical reason it can fault before CPU effects.
Explicit init begins a new observation profile and clears accumulated reasons.

Run `node --test web-player/tests/attiny13a-clki-validation.test.mjs`.
