# Lazy watchdog clock synchronization: implementation audit

Audited against native sources at `77c354b`; no lazy implementation or speed
claim yet. The rejected [period-cache experiment](../reports/watchdog-period-20261025.md)
keeps the eager implementation. This follow-up would defer oscillator-coordinate
conversion while the watchdog counter is off, then recover the exact phase
before a consumer needs it. It must not change observable source edges, AVR
instruction cycles, event ordering, diagnostics or buffered output.

## Clock contract and proposed representation

`base_frequency()` is fixed for an initialized instance:1e12 in physical mode,
otherwise2*configured oscillatorHz. OSCCAL/CLKPR alter source/CPU timing, not
that base coordinate. WatchdogHz is also configured before initialization.
Keep the original numerator remainder and rational conversion. A private
last-synchronized base timestamp would permit exact catch-up using the elapsed
delta; never multiply an absolute timestamp by the watchdog rate. Device init
clears this epoch; MCU reset must retain it.

The existing model advances its oscillator coordinate while the counter is
off. Defer calculation, not this coordinate or its fractional phase. At an
off→on transition, first synchronize to the bus timestamp and advance the
still-disabled module to that coordinate. Only then apply the control write.
Otherwise disabled history will be charged against the newly enabled timeout.
Catch-up must be idempotent at the same timestamp.

## Consumers and coherence boundaries

| Consumer | Required behavior before deferring arithmetic |
| --- | --- |
| `elapse` in peripherals/device.c | Convert eagerly when WDE/WDTIE is active; preserve existing source→ns→watchdog fault order. Record the deferred interval only for eligible off-state clocks. |
| `service_async` | Reset-held/startup holds the counter at zero while oscillator phase advances. Off-state service still advances CPU time; avoid replaying held intervals when reset releases. |
| `clki_service` in devices/attiny13a/clki_board.inc | Its second watchdog advance at the same base timestamp updates CPU-cycle windows after a delivered phase; zero oscillator delta does not make this call redundant. |
| `device_write`: WDTCR and MCUSR | Synchronize before the real masked write. WDRF/WDTON can force WDE. Discard off-state oscillator history before enabling; retain W1C and protected-window semantics. |
| `device_read`: WDTCR and MCUSR | Keep CPU-time/window expiry coherent; reads do not themselves need a watchdog pulse counter, but must not accidentally replay deferred time. |
| `device_control`: WDR | Synchronize the module's clock coordinate before clearing its counter; WDR does not reset oscillator phase. |
| `reset_state` and `power_sync` HOLD | Synchronize before system_watchdog_reset; retained global phase must reach the exact assert/hold timestamp. Initial zero-epoch reset remains valid. |
| `reset_startup` | Synchronize before calculating watchdog phase after the internal WDT-reset pulse. Do not confuse numerator phase with elapsed base ticks. |
| `clki_reset_startup` | Synchronize before asynchronous SUT deadline computation, including direct calls after an external source rise releases stretched WDT reset. |
| `next_event_scan` | Active timeout uses a current remainder. WDCE expiry remains a separate CPU-cycle deadline even when WDE/WDTIE are clear. |
| IRQ/pending/mirror/wake | Flags/control remain coherent after active service; do not suppress them just because the counter later becomes off. IRQ ack can alter WDTIE. |

`device.h` exposes no raw watchdog tick/remainder getter. Architectural state,
I/O, IRQs, faults and clock/reset deadlines remain observable through existing
APIs. Audit fixtures which inspect private board fields: explicit synchronization
may be necessary for such an observation, but changing a fixture must not weaken
the free-running phase or enable/reset equivalence checks.

## Fault and expiry constraints

Blindly skipping `system_watchdog_advance` while off is unsafe: its `cpu_time`
expires WDCE after four CPU cycles and detects reversed CPU time. The CLKI
second-service path must still observe newly delivered CPU phases. A lightweight
off-state service needs to preserve these effects even when oscillator division
is deferred.

For valid zero-epoch time and R<=B, the cumulative oscillator quotient
floor(base*R/B) fits uint64 whenever base does. A delayed conversion therefore
cannot introduce a quotient/counter overflow that an earlier eligible interval
would already have raised. R>B must retain eager conversion: both quotient
and tick-add overflow can occur before the base limit. First-fault ordering,
post-fault clock continuation and test-seeded invalid private states need explicit
coverage; this bound alone is not permission to change their diagnostics.

Power/reset input changes settle before delivered CLKI sampling at ties. Lazy
catch-up must occur at those existing boundaries; do not move an effect to a
later CPU instruction or cross a pin-buffer yield. Current event-cache
invalidation rules remain authoritative.

## Admission checks for a prototype

1. Independent BigInt fractions/uint64 tests for both contracts and arbitrary
   rates, retaining the new eager-clock regression as an oracle.
2. Off→on/off→on at fractional timestamps: first watchdog pulse/timeout at the
   original edge, no charge for disabled history. Test WDR and WDTCR/MCUSR.
3. WDTON/WDRF forced enable, four-cycle WDCE expiry while off, masked writes,
   combined interrupt/reset mode and ack behavior.
4. Internal and CLKI reset assert/hold/release, power causes, fuse SUT and
   stretched WDT pulse. Keep CPU half-phase, OSCCAL/CLKPR and source transitions.
5. Full suite and expanded15-case PCM/state/pin/IRQ/ADC parity matrix, then
   balanced native identity timings. No default activation from a synthetic
   gain; require IRQ-active browser underrun checks before a real-time claim.

Manufacturer source: [ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections6.2 (watchdog-based startup) and8.4–8.5 (watchdog modes, WDRF/WDTON and
protected writes); addresses/masks remain from the pinned official DFP3.4.278.
The off-state oscillator phase policy is an existing digital model choice;
silicon phase uncertainty is not resolved by lazy arithmetic.
