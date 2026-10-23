# ATtiny13A analog RESET input profile

This standalone receiver evaluates RESET voltage relative to VCC in a physical
1ps time domain. It does not own GPIO, fuses, reset flags, POR/BOD, CPU state,
startup delays or external programming interfaces.

## Manufacturer evidence

The primary reference is [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf):

- Section8.2.2, printed page43/Figure8-4: external RESET works without the
  system clock. Short pulses are not guaranteed to reset; release starts the
  reset timeout after the rising input reaches its reset threshold.
- Table18-4, printed page126: threshold bounds0.2..0.9VCC; minimum recognized
  pulse width has typical2000/700/400ns at1.8/3/5V and maximum2500ns.
- Figures19-55..58, printed pages158..159: typical RESET thresholds,
  hysteresis and pulse width versus voltage/temperature. Section19 says these
  characteristics are indications rather than production-tested guarantees.
  Figures19-48..50 describe RESET **as GPIO** and are a different receiver.

These sources do not specify exact assertion latency, internal filter topology,
or a guaranteed RESET hysteresis curve. In particular, tRST is not an exact
propagation delay. [DS80000857A](https://www.microchip.com/DS80000857) adds no
RESET clarification.

## Explicit profile choices

There is no default or typical profile constructor. The caller supplies:

| Field | Meaning |
| --- | --- |
| `assert_threshold_ppm` | Low-going Schmitt threshold as millionths of current VCC |
| `release_threshold_ppm` | High-going threshold; its difference from assert specifies hysteresis |
| `assert_qualification_ps` | Continuous low Schmitt-state qualification |
| `release_qualification_ps` | Continuous high Schmitt-state qualification |
| `assert_propagation_ps` | Additional inertial assertion stage |
| `release_propagation_ps` | Additional inertial release stage |

Both thresholds lie within the published span and assert is strictly less than
release:200000<=assert<release<=900000. Comparisons use exact signed64 cross
products; fractional-microvolt thresholds are not rounded. Equality belongs to
the low side at assert and the high side at release. Voltage between thresholds
retains the previous Schmitt state, initially released.

The two-stage **inertial** model is a declared simulation choice. A candidate
first qualifies, then propagates; the qualified output changes only after both
stages. An opposite Schmitt transition cancels either stage, so a pending stale
assertion never appears after the input returns high. Motion within the band
does not restart timing. This is not a claim about unpublished silicon filter
internals or short-pulse behavior of every chip. For a selected profile the
required stable interval includes both explicit durations. Neither duration is
automatically set to a value from Table18-4.

VCC0 cancels pending work and releases this receiver immediately; POR owns the
unpowered device. A later positive supply starts fresh qualification from the
released Schmitt state. Negative VCC is invalid. Signed32 RESET voltages are
accepted numerically, but the module does not simulate clamp currents, damage,
input loading, floating voltage, or validate operating/absolute-maximum ratings.
Outside the datasheet operating conditions its result remains this selected
numerical profile, not assured physical chip behavior.

## Board integration contract

Use `attiny13a_reset_input_init`, `set_voltage`, `advance`, `next_deadline` and
`asserted`. Both RESET and VCC are passed atomically to `set_voltage`, including
when an undriven RESET follows its pull-up supply; updating the two rails
separately can invent intermediate states. Inputs are piecewise constant and
chronological. A due deadline is processed before an input at the same ps.

Add the returned next deadline to the board's event minimum. Advance to each
deadline and observe the scalar output before applying equal-time inputs; feed
the result as an already-qualified EXTRF source to the existing reset aggregator.
The owner still gates RESET by its latched pin role/RSTDISBL and handles any
independent prequalified digital bypass. A true low level remains asserted;
CPU reset acknowledgement must not reinitialize this voltage receiver. Start
SUT only after all aggregate sources release, and add no timeout in this module.

`phase`, `raw_low`, `qualified`, `deadline_ps`, `last_change_ps` and sticky
`fault` are observable diagnostics. `qualified` identifies the propagation-stage
candidate, while `asserted()` is the actual output to aggregate. The optional
`take_changes` latch records ASSERT/RELEASE kinds, including both kinds when
zero-delay/equal-time inputs are batched. It is not an event history and does
not replace chronological scheduling. A stable span is O(1), with at most the
qualification and propagation boundaries; CPU clocks and host callbacks are
unnecessary.

UINT64_MAX means no deadline and is not a valid input timestamp. Deadlines
cannot reach this reserved value; overflow, backwards time, invalid input and
invalid profiles latch explicit faults. A fault freezes the output and returns
no further deadline; the board must surface the fault rather than accept the
frozen output as verified hardware state. Only a new explicit init clears it.
