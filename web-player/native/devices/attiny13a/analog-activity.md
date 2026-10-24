# Planned ATtiny13A analog activity contract

Saved 2026-10-24. This is a proposed implementation contract for the
[peripheral activity plan](../../ATTINY13A_PLAN.md), not an implemented feature
or a completed acceptance item. It changes neither the current native runtime
nor its WASM artifact.

## First implementation boundary

Omit a disabled ADC only from recurring advancement in
[`analog_advance`](../../peripherals/analog.c) and its deadline query in
`analog_next_event` when `ADCSRA.ADEN=0`. Keep comparator advancement and all
timestamped ADC bus, control, reference, input and trigger operations. Do not
extend this first change to an enabled but idle ADC, clock-gated conversions,
the comparator or the entire combined analog scheduler.

The existing [`analog_adc.c`](../../peripherals/analog_adc.c) supplies the
invariant: reset creates ADEN=0 and IDLE; a write clearing ADEN aborts any
conversion, clears ADSC and restores first-conversion state. `request` cannot
start a conversion with ADEN clear, and only a register write can enable it.
The disabled ADC therefore has no timed conversion work to service. Preserve
the existing rejection of reversed timestamps.

Hardware basis: [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 7.5.2, 13.1, 13.2.2, 14.4, 14.5 and 14.12: clearing ADEN disables
the ADC and terminates conversion; its prescaler is reset while ADEN is clear
and runs while ADEN is set. ACME uses ADC inputs when ADEN is clear. PRADC
also prevents comparator use. Interrupt flags and their enable bits have
separate roles. These hardware rules motivate the proposed optimization;
the source code and tests define this model's explicit digital phase policy.

## Catch-up before mutation and observation

Keep the existing `analog_adc_advance` call inside each timestamped component
API: `analog_adc_read`, `analog_adc_write`, `analog_adc_input`,
`analog_adc_reference`, `analog_adc_sources`, `analog_adc_ack`,
`analog_adc_clock_running` and `analog_adc_noise_cancel_start`. Their complete
signatures and time contract are in
[`analog_adc.h`](../../peripherals/analog_adc.h).

Only private disabled-state time bookkeeping may remain behind during an
omitted recurring advance. Before ADEN is enabled, the register-write path
must catch up through the actual write timestamp under the previous clock
state, then establish the new prescaler origin. An enabled ADC retains its
continuous phase between conversions. Do not reset its origin merely because
ADSC is clear or the next conversion deadline is absent.

[`device.c`](../../peripherals/device.c) owns PRR, sleep and reset transitions
through `clock_domains`. It calls `analog_adc_clock_running` before changing
the component's clock gate. Retain that catch-up on both gate transitions so
stopped intervals are excluded from future conversion phases. Keep sleep-entry
`analog_adc_noise_cancel_start` and its eligibility checks. This step does not
alter clock-domain selection, source-edge delivery or CPU continuation timing.

## Dependencies that remain live

- `analog_pending` and `analog_adc_pending` must keep their existing ADIF/ADIE
  logic even with ADEN clear. Preserve retained results, ADCL/ADCH locking,
  W1C behavior and vector acknowledgement; inactivity must not clear a flag.
- `analog_sources` and `connect_sources` must retain changed comparator,
  Timer0, INT0 and PCINT flag levels while the ADC is disabled. Held flags,
  clearing edges and ADTS/ADATE writes affect later trigger detection. The
  `analog_adc_sources` API catches up before changing those levels. Update
  `connect_sources`' current comment if recurring ADC advancement is omitted:
  its callers will no longer necessarily have advanced a disabled ADC.
- `analog_input` must keep updating ADC channel voltages and comparator PB
  voltages, including PB3/ADC3 on every required CLKI transition. Preserve
  `analog_reference` and equal-time ordering: existing sampling is processed
  before an input/reference mutation at the same timestamp.
- [`analog_comparator.c`](../../peripherals/analog_comparator.c) remains
  independent of ADC conversion activity. `analog_comparator_adc` must still
  receive ADEN, ACME and MUX changes after ADC-register writes; a disabled ADC
  can supply the comparator's selected negative input. Preserve ACI/ACIE,
  bandgap startup, analog propagation and digital synchronization.
- Keep comparator advancement even with ACD set for this first step. Its
  current `half_cycle` then remains the combined scheduler's monotonic-time
  anchor when ADC bookkeeping is lazy. Omitting both components would require
  an explicit replacement for that shared time validation. Comparator
  `clock_running=0` alone is insufficient to skip it: its analog propagation
  can continue with digital synchronization stopped. ACD/sleep disable cancels
  its deadlines, but optimizing that case is a separate change.

Repeated calls at one timestamp must still settle newly scheduled zero-delay
comparator work. Keep the chronological merged-event loop in `analog_advance`;
do not replace it with a blanket same-time early return.

## Required evidence before acceptance

Compare the proposed board with an unconditional-service reference after bus,
input and clock-domain operations. Cover long disabled intervals and reenable
on both CPU half phases; abort/reenable and first-conversion timing; every ADC
divider; retained ADIF with ADIE; ADCL locking; ADTS/ADATE writes and held/set/
clear trigger levels; all ACME channels; PRR and sleep/resume; reference changes;
and a voltage mutation exactly at the sampling edge. Exercise internal clocks,
held/irregular CLKI, GPIO/VCC propagation, reset and newly created zero-delay
events. Compare registers, deadlines, sampled/completed timestamps, pending
IRQs, wake/reset state, memory, pin history and PCM where applicable.

For private-state parity, advance a copy of the disabled ADC to the observation
timestamp with the original `analog_adc_advance`, then compare the complete
state against the reference. This accounts for intentionally deferred
`half_cycle` and clock-gated `origin` bookkeeping without excluding origin or
other phase fields from verification. Do not settle the production instance
solely to make an assertion pass. The current raw-state oracle in
[`device-analog-propagation.test.mjs`](../../../tests/device-analog-propagation.test.mjs)
will need this explicit normalization if the change makes its disabled ADC
timestamps lazy.

Retain the existing
[`analog-adc.test.mjs`](../../../tests/analog-adc.test.mjs),
[`analog-comparator.test.mjs`](../../../tests/analog-comparator.test.mjs) and
[`attiny13a-analog-deadline.test.mjs`](../../../tests/attiny13a-analog-deadline.test.mjs)
boundary coverage, then run the full regression suite. Add native entry
counters proving that recurring disabled ADC advances/deadline calls disappear
while required input/trigger calls and source edges remain. The retained
[current counter trace](../../../reports/planned-optimizations-20261024/call-counts-and-prefix.json)
is a baseline observation, not evidence that this planned change is present.

Counters include source entries that the compiler may inline; they establish
removed work, not WASM call cost or speedup. Establish any speed claim with
serial alternating uninstrumented old/new runs, identical firmware/input/
sample intervals, exact state/PCM parity and retained individual paired
timings. Activity guards must justify their own branch cost. Keep small gains
within host variation inconclusive.
