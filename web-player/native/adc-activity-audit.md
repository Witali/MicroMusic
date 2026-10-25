# ADC recurring-service audit

Next experiment after the [rejected lazy watchdog conversion](../reports/watchdog-lazy-20261025.md).
Native production remains `953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0`.
No ADC gating implementation or performance claim yet.

Separate entry traces show 4.41–4.60M `analog_adc_advance` entries per 250ms
of the three retained physical firmware images, and 5.00–5.60M per 25ms of
20MHz CLKI kernels. The rejected watchdog candidate leaves these counts intact.
Counts identify recurring work; they neither establish its exclusive cost nor
prove the ADC was disabled throughout each run. Record enabled/disabled activity
before estimating removable work.

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

## Next safe implementation step

First add a diagnostic split for disabled/enabled-idle/converting ADC entries;
sampled or counted code must remain separate from benchmark binaries. Then
prototype one aggregator optimization against an unconditional reference using
the actual ADC/comparator modules. Keep explicit first-sample27/29 profiles,
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
