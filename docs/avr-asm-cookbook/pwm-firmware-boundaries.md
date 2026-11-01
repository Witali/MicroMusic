# Check PWM boundaries through actual AVR firmware

Target: ATtiny13A, the connected native Timer0/GPIO board and generated AVR-to-WASM
CPU. This is correctness evidence, not an assembly optimization or speed claim.
Instruction/register constants come from the pinned Microchip ATtiny_DFP 3.4.278
definitions; no alternative register addresses or programming interface is used.

The hardware references are [DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
sections 11.5–11.7, Table 11-8 and the compare timing diagrams. The table was also
checked visually in the cached official PDF: this chip specifies TOP for OCR
buffer updates in both PWM families. That is different from assuming another
AVR device's Timer0 behavior. The existing model's TOP-to-BOTTOM Fast PWM output
restoration interpretation remains explicit; these tests do not settle the
summary-table wording or dynamic TOP behavior on silicon.

The [source fixture](../../web-player/tests/fixtures/attiny13a-pwm-boundaries.mjs)
uses a small AVR image to write DDR/COM/OCR/TIMSK, preload OC latches with non-PWM
FOC strobes and start Timer0 at a known final OUT boundary. TCNT is not written,
so no write-induced compare suppression is introduced. The overflow ISR changes
a GPR and returns while PWM continues. Both selected output pins remain observed;
the other channel holds a constant extreme as a control.

The reference is closed-form arithmetic, independent of `timer0.c` and of a
second emulator. With TOP `T`, compare `K` and pulse count `n` from startup:

- Fast PWM period is `T+1`; a middle compare changes output at `K+1`, with
  restoration at the next period boundary.
- Phase-correct period is `2*T`; middle transitions are at `K+1` and
  `2*T-K+1`, using the existing documented compare-pulse phase.
- Extreme compare values use their separate constant/spike rules. Non-PWM
  preload avoids making undocumented first-latch initialization assumptions.

Invert levels for inverted output, repeat over three periods and compare every
selected-pin timestamp. An asymmetric CLKI fixture (300 ns high, 700 ns low)
shares the one-microsecond rising-edge period with the internal digital fixture.
This tests the actual clock-phase path without extrapolating CLKI from Hz.

The [retained result](../../web-player/reports/pwm-boundaries-20261101.md)
covers 144 firmware cases, 72 policy pairs and 408 compared pin events, with
264 active IRQs. Both full state/data and traces agree across conservative and
optimized CPU policies. The complete suite passes 3025/3025. All timings concern
the selected digital fixtures: no silicon calibration, dynamic OCR update,
WGM5/TOP0, complete internal-phase oracle or audio-underrun acceptance follows.
