# Pending hardware probe: Timer0 WGM5 with TOP=0

Status: **pending hardware**. No silicon results or predicted TOP=0 waveform are
supplied. `timer0-top-zero-probe.S` is measurement firmware, not an emulation
implementation. `timer0-top-zero-probe.json` lists reproducible build profiles,
stimulus settings and the expected **record format**, with
`expectedSiliconTrace: null`.

## Official documentation gap

[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
section 11.7.4, PDF pages 73–74, describes reversing direction at TOP, a
one-timer-clock TOP interval, TOV at BOTTOM and the output polarity when OCR0A
is zero. Table 11-8 on page 79 gives OCR0A as TOP in WGM5 and OCR updates at TOP.
These statements do not explicitly resolve simultaneous TOP=BOTTOM precedence,
the counter sequence, overflow frequency, toggle frequency or buffer-transfer
cadence in that degenerate case. In particular, an output duty extreme alone
does not establish counter/IRQ timing.

[ATtiny13A Silicon Errata and Data Sheet Clarification DS80000857A](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/Errata/ATtiny13A-SilConErrataClarif-DS80000857A.pdf)
lists the low-voltage EEPROM issue and no data-sheet clarifications; it does not
add a Timer0 TOP=0 definition. The current emulator's explicit fault remains
until an authoritative clarification or observed trace settles this corner.

## Wiring and stimulus

Use an ATtiny13A with low/high fuses **7a/ff**, lock **ff**, the normal RESET role
enabled, and a measured stable supply. Firmware also requests CLKPR=/1. Record
the actual device marking/revision if available, fuse readback, VCC and operating
temperature. Nominal internal clock frequency is 9.6 MHz; it is not a calibrated
measurement. Match generator/analyzer logic levels to VCC and share ground.

| Pin | Role |
|---|---|
| PB0 / OC0A | Capture the actual compare output continuously |
| PB1 / OC0B | Capture the second compare output continuously |
| PB2 | Serialized trace clock, idle low |
| PB3 | Serialized trace data, sampled at PB2 rising edges |
| PB4 / T0 | Generator input: externally stepped rising timer clocks |
| PB5 / RESET | Normal reset/programming role |

Release programmer drive on shared ISP pins before acquisition; those pins
become the probe's GPIO/compare outputs when RESET is released.

Keep T0 low during reset and initialization. Begin the pulse burst only after
receiving the complete boot frame. Use the configured 100 Hz stimulus: 5 ms
high, 5 ms low. Both phases must be at least 1 ms so sampling and serialization
finish before the next edge. Select rising-edge Timer0 clock only; the falling
edge merely lets firmware arm its next sample. Capture all five digital signals
before reset release, with trace clock and T0 initially low; 20 MS/s is suitable
for resolving the short trace-clock pulses at the nominal CPU frequency.

The firmware disables interrupts, watchdog, ADC and comparator. It initializes
OC latches with non-PWM FOC, writes OCR registers while double buffering is off,
then selects the requested phase-correct mode and external T0. It normally leaves
TCNT0 at its reset value, avoiding the first-pulse compare suppression caused by
an explicit TCNT write. The `zero-top-from-counter-two` profile deliberately
writes TCNT0=2 and therefore includes that documented one-pulse suppression.

After detecting each T0 high, firmware waits 32 CPU clocks, then reads raw
TCNT0, TIFR0, PINB, OCR0A/B and TCCR0A/B. That wait exceeds the documented T0
synchronization delay without choosing an exact asynchronous phase. It saves
the observations, clears TIFR0 bits 1–3 with W1C, and serializes a record. No
Timer0 clock occurs during the observation interval because T0 remains high.

## Profiles and build

Run both controls before interpreting TOP=0 measurements:

- `control-fixed-top-255`: WGM1, fixed TOP, both non-inverting outputs.
- `control-variable-top-3`: WGM5 with a nonzero TOP and OC0A toggle.
- `zero-top-toggle`, `zero-top-noninverting`, `zero-top-inverting`: direct zero
  TOP with different COM modes and deliberately chosen initial latch states.
- `zero-top-compare-b-one`: OCR0B=1 while TOP is zero.
- `zero-top-from-counter-two`: nonzero initial TCNT0 with zero TOP.
- `buffer-top-three-to-zero`, `buffer-top-zero-to-three`: one OCR0A write after
  sample 8, with an additional write-marker record at the same sequence index.

Definitions and burst lengths are canonical in the JSON file. Each profile
should be rerun from reset; do not reuse the previous run's hidden timer state.
Preserve raw analyzer files as well as decoded values. Do not substitute an
emulator-generated trace for a silicon observation.

From the repository root, the default zero-TOP toggle profile builds as follows
(put all generated outputs under ignored `build/` or an external lab directory):

```text
avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-e,__vectors web-player/native/peripherals/timer0-top-zero-probe.S -o build/probe.elf
avr-size build/probe.elf
avr-objcopy -O ihex -R .eeprom build/probe.elf build/probe.hex
```

For another profile, append each JSON `defines` entry as `-DNAME=value` before
the source path. For example the nonzero control uses `-DPROBE_MODE=5
-DPROBE_INITIAL_TOP=3 -DPROBE_OCR0B=1 -DPROBE_COM0A=1 -DPROBE_COM0B=2
-DPROBE_INITIAL_LEVELS=0`. Program using the lab's existing programmer and verify
readback. Source is retained here; no ELF/HEX/binary is committed. Record source,
configuration and programmed-image SHA-256 values with every physical capture.

All nine configurations assemble with the repository's AVR GCC 7.3.0 toolchain:
442 bytes Flash for ordinary profiles, 446 for the TCNT-seeded case, 474 for
buffered-write profiles; zero static data/BSS. Stack use is at most two nested
return addresses (four SRAM bytes). Compilation establishes firmware size and
syntax, never the unknown Timer0 result.

## Record format and decoding

Each frame is 14 bytes, MSB first: sync **a5 5a**, then 11 payload bytes and one
XOR checksum. Payload order:

| Byte | Field |
|---|---|
| 0 | Wire version, 1 |
| 1 | Type: 0 boot, 1 sampled pulse, 2 scheduled OCR0A write |
| 2–3 | External pulse sequence, little endian, modulo 65536 |
| 4 | Raw TCNT0 |
| 5 | Raw TIFR0; bit1=TOV, bit2=OCFA, bit3=OCFB |
| 6 | Raw PINB; bit0/1 provide sampled compare-pin levels |
| 7–8 | OCR0A/B CPU-visible register readback |
| 9–10 | TCCR0A/B |

The checksum XORs the 11 payload bytes. Register readback does not reveal the
hidden active OCR buffer or direction bit; infer neither from it alone. The
OC0A/B waveform must remain in the original capture to locate physical changes
relative to external T0 and the serialized observation. `frameEndSeconds` is a
transport timestamp, **not** the timer event's timestamp.

Export edge/sample CSV with columns `time_s,clock,data,t0,oc0a,oc0b`. Digital
values must be 0/1; timestamps must be finite seconds in monotonic order. The
decoder requires `time_s,clock,data,t0` and retains a reference/hash to the full
waveform containing OC0A/B. Capture boot plus the complete configured pulse burst
and its final frame; do not stop in the middle of a serialized record.

```text
python web-player/native/peripherals/timer0-top-zero-probe-decode.py capture.csv --profile zero-top-toggle --capture-kind hardware -o observed.json
```

The decoder checks sync, checksum, record order, pulse counts and scheduled-write
markers. It preserves counter/flag/output observations without comparing them
to a guessed TOP=0 model. Add measured conditions and instrument settings under
`measurements`; the JSON configuration embeds the trace schema. Synthetic
decoder checks must use `--capture-kind synthetic` and receive a different
status, so they cannot silently become hardware evidence.

```text
python web-player/native/peripherals/timer0-top-zero-probe-test.py
```

These four protocol tests cover arbitrary observed counter bytes, checksum
corruption, dropped pulse records and truncated captures. They supply no
physical Timer0 results. A future implementation must cite the actual observed
capture, check repeatability from reset, reconcile the two controls and preserve
any silicon-revision differences before replacing the existing fault.
