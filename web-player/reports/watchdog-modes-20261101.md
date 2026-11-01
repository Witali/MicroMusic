# Watchdog firmware and stopped-clock audit

Microchip [DS40002307A sections8.4/8.5.2](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=48)
distinguish flag clearing, counter restart and vector execution. This audit adds
20 full-board firmware checks to the existing standalone controller tests.
No runtime correction was needed. Native bytes, compiler/cache identity and ABI
remain exactly those of baseline `4218953a`.

The new firmware uses the manufacturer-derived WDTCR/MCUSR/port masks, enters
Power-down, reads WDTCR before/after service and toggles PB4 in its ISR. Tests
observe flags, CPU progress, stack restoration, IRQ/reset counts and physical
pin snapshots. Sixteen cases combine four programs, both CPU policies and
internal/external clocks. Four additional cases hold CLKI high or low.

| Program | Verified software outcome |
| --- | --- |
| Interrupt-only | Two vector entries, WDTIF acknowledged, WDTIE retained, two PB4 transitions, no reset |
| Serviced combined | ISR sees WDTIF/WDTIE cleared and WDE retained; next timeout resets ports and CPU |
| Unserviced combined with W1C | Firmware clears WDTIF without entering its vector; the next timeout still resets |
| WDR after that W1C | Counter restarts, but the unserviced combined history remains; reset follows the new counter deadline |
| CLKI held high/low | WDTIF becomes pending without an ISR/retirement; next timeout releases GPIO independently of CLKI; restart waits for delivered source phases |

The explicit profile uses a 1 MHz CPU, 128 kHz watchdog and zero startup delays.
WDT is enabled before oscillator pulse 1. The first two deadlines are 16 ms and
32 ms. WDR at 16.009 ms follows pulse 2049, making the new reset deadline
pulse 4097 / 32.0078125 ms. Tests compare the final picosecond before reset with
the reset instant and require the port-release snapshot at that exact instant.
The held clock resumes at 40 ms; both levels boot again without an intervening
ISR. These values establish the selected digital fixture, not measured chip
frequency, analog reset pulse width or internal silicon phase.

All **121 focused checks and 2833/2833 default tests pass**, including the new
20. Related retained suites
cover ten prescalers, WDTON/WDRF forcing, protected writes, flag acknowledgment,
fractional oscillator accumulation, startup/reset and Power-down domains.
The [evidence record](watchdog-modes-20261101.json) pins the native artifact,
build manifest, compiler identity, test/fixture sources and TAP hashes.

Reproduce the added firmware checks:

```sh
node --test web-player/tests/attiny13a-watchdog-modes.test.mjs
```

The audit uses the already registered manufacturer datasheet/device definitions;
there are no downloads, new tools or hardware programming. The cookbook retains
the [clock-separation technique](../../docs/avr-asm-cookbook/watchdog-clock-separation.md).
The watchdog README's stale pre-integration statement is corrected. No hardware,
official-simulator or performance acceptance item closes; the plan remains
**24/31 complete, seven open**.
