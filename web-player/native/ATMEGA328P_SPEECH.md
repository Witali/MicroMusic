# ATmega328P speech player

The speech collection (`?collection=hq4`) includes an Arduino Uno / Nano
ATmega328P profile at 16 MHz in the existing device selector. The music
collection retains its ATtiny13A / ATtiny88 choices.

`firmware-atmega328p.json` contains actual linked Flash images and direct HEX
downloads. The Arduino path executes these images; it does not substitute a
decoded WAV. The original recording remains a separate listening comparison.
Unused EEPROM has a visible, disabled download control.

| Player | Sample clock | PWM output | Arduino header |
| --- | --- | --- | --- |
| LPX | Timer1 COMPA, 8 kHz | Timer2B, 62.5 kHz | D3 / PD3 |
| Speex | Timer2 COMPA, 8 kHz | Timer1A, 62.5 kHz | D9 / PB1 |

The generated catalog records the output for each image. The UI uses it for
pin labels, the OCR scope tap and the physical output. Flash accounting shows
program bytes, complete encoded bytes and their sum; the capacity is 32 KiB.
SRAM is 2 KiB and EEPROM is 1 KiB. Board fuses are retained rather than using
the ATtiny13A defaults.

## Execution and timing boundary

- `lib/atmega328p-profile.js` holds immutable device geometry without loading
  the CPU package into other device pages.
- `lib/atmega328p.js` combines the pinned [AVR8js 0.21.1 runtime subset](../vendor/avr8js/0.21.1/README.md)
  with its actual ATmega328P timer/GPIO/EEPROM configuration. It keeps 32 KiB
  program memory and the real 2 KiB SRAM, including the register/I/O region.
- `tickATmega328P` preserves the existing Speex test oracle's bounded IRQ
  correction: clock events progress while an interrupt is deferred for the
  instruction after SEI/RETI, and IRQ entry consumes four cycles. The upstream
  runtime files remain unchanged apart from browser import extensions.
- `lib/renderer-atmega328p.js` integrates physical PWM pin high time over each
  host audio frame and retains a separate time-averaged OCR tap. It reuses the
  existing audio filters and control smoothing.
- `lib/arduino-speech.js` validates memory limits, the complete Flash/audio
  split, engine identity, timer pin pair, exact bitrate and source-bound assets.
  Native WAV entries cannot pass this firmware boundary.
- `playbackCycles` is the measured full firmware duration, including startup
  and queue drain. One-shot transport uses this duration rather than cutting
  the final samples at the encoded content duration.

The Arduino engine is selected explicitly as `avr8js`. Other engines reject
ATmega328P entries; AVR8js rejects Tiny entries. Returning to a Tiny device
restores the previous supported engine. No Tiny88 memory map is repurposed.

This subset supports the peripherals used by these speech images. It does not
claim a complete ATmega328P board model or verification on a physical board.

## Verification

`tests/atmega328p.test.mjs` exercises original synthetic AVR5 machine code with
hardware MUL, active sample IRQs, concurrent PWM timers, both output pins,
stack bounds, sample-clock drift, filtering and arbitrary audio block splits.
`tests/signal-point.test.mjs` runs both timer configurations through the actual
Worker, controls and audio-port path. These fixtures test emulation, not codec
quality.

`tests/arduino-speech.test.mjs` exercises the shared dropdown, root/Pages deep
links, exact downloads, engine restoration, complete one-shot playback and
catalog errors/races. Legacy music, speech and native LPX controls remain in
their existing regression suites. The postponed 1.5 kbit/s experiment is
omitted from the library; archived explicit links retain its format notice.

Actual images are built and admitted separately by
[`tools/build-arduino-speech.py`](../../tools/build-arduino-speech.py) and
[`scripts/verify-arduino-firmware.mjs`](../scripts/verify-arduino-firmware.mjs).
Admission compares every output byte against the independent native decoder
with the image's sample/PWM interrupts active, checks timing and SRAM/stack,
and rejects underruns. Logs, input paths, source fingerprints and local
oracles stay in ignored build directories. A host wall-time result describes
that host; it is separate from the emulated AVR's real-time budget.

Device reference: [Microchip ATmega328P](https://www.microchip.com/en-us/product/ATmega328P).
The IRQ correction also follows the rationale retained in
[`Codecs/Speex/AVR/tests/avr_tick.mjs`](../../Codecs/Speex/AVR/tests/avr_tick.mjs).
