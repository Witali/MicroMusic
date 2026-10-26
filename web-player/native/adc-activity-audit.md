# ADC recurring-service audit

The running-idle aggregator shortcut is retained at `14da787`, following the
[rejected lazy watchdog conversion](../reports/watchdog-lazy-20261025.md).
Native production is `b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4`.
See [verification, timings and the synthetic regression](../reports/adc-idle-20261025.md).
Broader ADC activity gating remains unimplemented.

Separate entry traces show 4.41–4.60M `analog_adc_advance` entries per 250ms
of the three retained physical firmware images, and 5.00–5.60M per 25ms of
20MHz CLKI kernels. The rejected watchdog candidate leaves these counts intact.
The new activity split proves these entries are disabled with a running source.
After the shortcut, music retains 37,479–37,494 module entries and the CLKI
kernels retain 1M. A separately enabled-idle CLKI control also drops 5.60M→1M;
the converting control retains all 5,609,415 entries. Counts do not establish
exclusive cost or a universal gain. Clock-gated counts are zero in these
captures; stopped-clock correctness has separate differential coverage.

## Source audit

`analog.c` owns the ADC/comparator event merge. `analog_advance` checks both
module timestamps, services each event through the requested time, propagates
comparator trigger flags at that event, then advances both modules to the final
time. A comparator event must not become an opportunity to skip a simultaneous
ADC sample or completion. `connect_sources` assumes ADC time is already current.

Every ADC read, write, input, reference, source, ack, clock-domain switch and
noise-cancel start first calls `analog_adc_advance`. The ADC's individual methods
already own their catch-up boundary. The aggregator nevertheless advances the
same module before many of these calls. Audit these duplicate advances and the
inactive recurring path separately; do not change several policies at once.

`analog_adc_advance` shifts origin and any pending edge during a stopped source,
then updates its timestamp. This bookkeeping is observable indirectly at resume.
`analog_advance`'s reversed-time check also depends on the module timestamps.
Skipping the call cannot silently weaken that check or treat a gated interval
as running ADC time.

| Boundary | Required invariant |
| --- | --- |
| ADEN=0 | A disabling write cancels conversion, clears ADSC and marks the next conversion first. Before enabling, recover exact bus time and origin. Preserve result/data-lock and flags, which need not disappear with ADEN. |
| ADEN=1, no conversion | Retain the enabled prescaler phase; being idle is insufficient to gate it. ADPS writes and a later ADSC request must use the existing edge calculation. |
| PRR/sleep/domain changes | Settle the old domain through the transition before toggling clock_running. Preserve shifted origin/pending edge, ADC Noise Reduction start and wake/IRQ behavior. |
| ADCSRB/ADMUX and comparator | Keep ACME routing and comparator input/reference changes even while ADC conversions are disabled. Disabling ADC does not disable the comparator. |
| Input/reference injection | Keep sampled-before-mutation endpoint ordering. Retain latest channel/reference values for a future conversion. |
| Trigger flags and ack | Keep flag-edge detection, held-flag behavior, ADATE/ADTS reconfiguration, W1C and ADC/comparator IRQ interaction at their original timestamp. |
| Read/result lock | ADCL locks and ADCH unlocks result publication. Catch-up cannot publish a discarded completion or move it past a read. |
| Reset/fault/snapshot | Reset cancels the old conversion once. Keep diagnostics and canonical observer behavior; normalize only genuinely private deferred timestamps in equivalence fixtures. |

## Implemented boundary and next work

`analog.c` now publishes only `adc.half_cycle` when the source runs, phase is
IDLE and time is nondecreasing. It retains origin and every other field exactly.
The original module function remains the path for converting, stopped or
reversed-time cases; the comparator and chronological event merge remain active.
There is no deferred timestamp, new state field or physical clock gating.

The new `analog-idle-dispatch.test.mjs` compiles the actual modules with an
unconditional reference from 238aab2 and compares all analog-state bytes, return
values, IRQs and deadlines. All 1,693 tests and 15 integration cases pass. Longer
music rows gain 1.028x/1.107x, while the synthetic internal 20MHz kernel is 0.942x.
No general performance gate closes. Next profile that negative kernel and audit
repeated publication/scanning before extending ADC dispatch reduction.

For further experiments keep explicit first-sample 27/29 profiles,
auto triggers, stopped/resumed domains, arbitrary reads/writes, reversed time,
held source flags, ACME and equal-time sample/input ordering in the oracle.
Prove fewer entries on real firmware and CLKI, not just in an isolated fixture.
Require the full suite,15-case PCM/state/pin/IRQ parity and balanced native
timings, including enabled-ADC controls. Browser IRQ-active underrun validation
remains necessary before a real-time/default-engine claim.

Manufacturer basis: [ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections13.1 and14. The ADC prescaler is held reset with ADEN clear and runs
while ADEN is set, including between conversions. ACME can route the ADC mux
to the comparator precisely when ADC is disabled. Those constraints rule out
gating solely on conversion activity. Existing register/mask definitions remain
from the pinned official Microchip DFP3.4.278, without manual address copies.
