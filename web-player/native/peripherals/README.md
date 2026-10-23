# ATtiny13A peripheral modules

These allocation-free C modules compile to WebAssembly without host imports.
They are developed and tested separately from the player's current `avr.c`
runtime. The translated player still uses that existing peripheral runtime;
adding these files does not yet enable full device emulation in the player.

The hardware reference is Microchip's
[ATtiny13A Data Sheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
Each module's documentation identifies its sections, timing assumptions and
explicitly unsupported or ambiguous cases.

| Module | Implemented behavior | API / detailed documentation |
|---|---|---|
| Timer0 | Six supported waveform modes, two compare channels, prescaler, external T0 clock, flags/IRQs, buffered compare registers, OC0A/B output transitions | [timer0.h](timer0.h), [timer0.md](timer0.md) |
| GPIO / external interrupts | Six pins, PORT/DDRx/PINx, pull-ups, DIDR0, timer overrides, INT0/PCINT, T0 input synchronization, bounded advancement over stable inputs | [system_gpio.h](system_gpio.h), [GPIO notes](system_gpio.README.txt) |
| Watchdog | Separate oscillator and CPU clocks, timed control writes, interrupt/reset/combined modes, WDR, WDTON and reset flags | [system_watchdog.h](system_watchdog.h), [watchdog notes](system_watchdog.README.txt) |
| EEPROM / Flash | EEPROM erase/write modes and CPU stalls, SPM protection windows and page buffer, asynchronous programming, fuse/lock reads, dirty Flash pages and generation | [nvm.h](nvm.h), [nvm.md](nvm.md) |
| ADC | Four analog channels, references, sample/hold and conversion timing, result lock, ADLAR, interrupt flags, free running and auto triggers | [analog_adc.h](analog_adc.h), [ADC notes](analog_adc.README.txt) |
| Analog comparator | Input and ADC mux routing, bandgap selection, configurable propagation/startup, clock synchronization, edge modes and interrupt flags | [analog_comparator.h](analog_comparator.h), [comparator notes](analog_comparator.README.txt) |
| Analog event routing | Comparator events trigger ADC at their original timestamps, entirely inside C/WASM | [analog.h](analog.h) |
| Sleep policy | Idle, ADC Noise Reduction and Power-down clock domains, wake sources, explicit startup and wake deadlines, PRR gating policy | [system_sleep.h](system_sleep.h), [sleep notes](system_sleep.README.txt) |

## Time and bus integration

CPU instructions retain their original AVR cycle counts. Event scheduling can
advance across a span in one operation only while preserving every intervening
observable event. It does not need a JavaScript call, or a loop over every CPU
cycle, to represent exact timing.

| API | Time domain |
|---|---|
| Timer0 | Absolute `uint64_t` CPU/clkI/O cycles |
| GPIO, ADC, comparator and analog routing | Absolute half CPU periods: cycle N corresponds to timestamp 2N |
| Watchdog | Independent watchdog oscillator pulses plus CPU cycles for protected writes |
| NVM | CPU cycles for protection windows plus elapsed nanoseconds for programming |
| Sleep | Uniform scheduler ticks selected by the embedding board; two ticks per CPU cycle matches the analog/GPIO domain |

The board scheduler must translate these domains from a common clock model,
preserving phase when CLKPR, sleep or power reduction changes clock availability.
It must split spans at external injections, I/O effects, peripheral deadlines
and interrupt arbitration. Input changes exactly at an event follow each API's
documented ordering. Nominal watchdog frequency or Flash programming duration
must not be derived from executed instruction count.

All register addresses in the APIs are I/O offsets; data-space addresses add
0x20. Route each register to one owner. GPIO owns MCUCR and DIDR0, analog owns
ADCSRB/ADMUX, and the board owns the canonical PRR/clock configuration. In
particular, OCR0A is I/O 0x36. The old player's 0x2a left-duty alias must not be
carried into the device bus.

The bus must preserve the selected write mask for SBI/CBI. A whole-register
read/modify/write is incorrect for PINB toggles, write-one-to-clear flags and
write strobes. The present translated player's two-argument `writeIO` import
must be extended before connecting these register semantics.

The CPU owns SREG.I, interrupt priority, SEI/RETI delay, stack writes and normal
entry latency. Module pending masks have different documented encodings and
must be converted to vector-word indices 1..9 before arbitration. A wake source
starts wakeup; after startup, arbitrate current live requests again. Do not force
an old INT0 request that disappeared during oscillator startup.

The generated CPU's SLEEP/SPM/WDR boundaries are ready to be connected to these
APIs. SPM must stop execution until Flash completion and retranslation of dirty
pages. Clearing a dirty mask does not make previously generated code valid.
The playback wait-loop accelerator currently assumes Timer0-only IRQs; use the
full scheduler's earliest deadline before enabling other peripherals in it.

## Output buffering

Timer0 writes timestamped OC latch/mux transitions into a caller-owned bounded
ring in WASM memory. Read/consume batches through `timer0_events` and
`timer0_consume_events`. An overflow increments `dropped_events`; the consumer
must report incomplete capture. Combine these transitions with GPIO DDRB,
PORTB, override and external-driver state to obtain physical pin levels.

The player's separate PWM batch path currently captures its historical OCR-duty
stream, up to 4096 mono/stereo frames per WASM call. Physical pin reconstruction
is part of connecting Timer0 and GPIO to the shared scheduler. Both output paths
avoid a callback into JavaScript for each transition or value.

## Verification and remaining integration

The tests compile the actual C sources with strict warnings and reject WASM host
imports. `peripherals-link.test.mjs` also links every module into one WASM and
checks their independent initial state. The suites exercise register behavior, boundary timing, asynchronous events,
sleep, interrupts, and randomized event-jump comparisons. They are specification
fixtures, not measurements of silicon. The first ADC sample phase is explicitly
configurable because section 14.5 and Table 14-1 disagree; comparator analog
delays and oscillator startup require board parameters.

Run from the repository root, with the prepared read-only Emscripten SDK (or
set `EMSDK`):

```powershell
node --test web-player/tests/timer0-peripheral.test.mjs web-player/tests/system-gpio.test.mjs web-player/tests/system-watchdog.test.mjs web-player/tests/nvm.test.mjs web-player/tests/analog-adc.test.mjs web-player/tests/analog-comparator.test.mjs web-player/tests/system-sleep.test.mjs
```

The shared bus/scheduler, whole-device reset and clock/fuse configuration,
BODCR sequence and electrical behavior, physical oscillator/reset delays and
debugWIRE remain device-integration work. The modules expose the required
boundaries without pretending that the existing player already implements them.
