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
| PB2 / T0 | Generator input: externally stepped rising timer clocks |
| PB3 | Serialized trace data, sampled at PB4 rising edges |
| PB4 | Serialized trace clock, idle low; sample data at its rising edges |
| PB5 / RESET | Normal reset/programming role |

Release programmer drive on shared ISP pins before acquisition; those pins
become the probe's GPIO/compare outputs when RESET is released.

The corrected mapping follows the pinned manufacturer's ATDF `TC0` signal `T`
on PB2 and data-sheet Figure1-1/Table10-3. The original probe swapped T0 and
trace clock, so serialization would itself clock Timer0. No hardware evidence
was retained from that mapping. Use the current firmware/configuration hashes;
do not interpret an older-pin-map capture using this acquisition procedure.

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

Run the nonzero controls before interpreting TOP=0 measurements:

- `control-fixed-top-255`: WGM1, fixed TOP, both non-inverting outputs.
- `control-variable-top-3`: WGM5 with a nonzero TOP and OC0A toggle.
- `control-variable-top-1-b-zero/one`: the nearest nonzero TOP, with each OCR0B
  extreme, to check boundary behavior without the TOP=BOTTOM ambiguity.
- `zero-top-toggle`, `zero-top-noninverting`, `zero-top-inverting`: direct zero
  TOP with different COM modes and deliberately chosen initial latch states.
- `zero-top-compare-b-one`: OCR0B=1 while TOP is zero.
- `zero-top-from-counter-two`: nonzero initial TCNT0 with zero TOP.
- `buffer-top-three-to-zero`, `buffer-top-zero-to-three`: one OCR0A write after
  sample 8, with an additional write-marker record at the same sequence index.
- `zero-top-pending-three-before-first-pulse`: initial active TOP=0, then OCR0A=3
  is written after selecting WGM5 but before any external pulse. Its boot frame
  reads back3; this does not establish when the hidden buffer transfers.

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

Addresses, register bits and RAMEND come from
`../attiny13a-registers.generated.inc`, derived from the pinned official
Microchip device definitions. No copied numeric register map is retained in
the probe. Stack use is at most two nested return addresses (four SRAM bytes).
Compilation establishes firmware size and syntax, never the unknown Timer0
result. The verification script below builds every profile and executes only
the nonzero controls as software smoke checks.

```text
node web-player/scripts/verify-timer0-probe.mjs
```

The script locates the prepared AVR GCC7.3.0 toolchain in an ancestor's
`build/toolchains/avr-7.3.0/bin`, or accepts `--avr-bin DIR`. Python must be
available for the existing protocol decoder; use `--python FILE` or `PYTHON`
to select its executable. Generated ELF/binary/CSV/JSON files stay under ignored
`build/timer0-probe-verification/`, overridable with `--out DIR`.

The 2026-10-24 run built all12 profiles, occupying442–474 Flash bytes with no
data/BSS section. Four nonzero controls executed their actual assembled firmware
in the full-device emulator and emitted a boot frame plus four pulse records
each. The verifier checks TCNT0/TIFR0 before any T0 stimulus, input/output
directions, framing/checksum/sequence, configuration readback, sampled PB2 and
the documented nonzero counter sequences. GPIO pin events are drained in bounded
chunks. These controls use the fixed nominal oscillator and explicit zero-startup
software fixture; each stimulus phase lasts40000 base half-cycles (about2.08ms),
above the acquisition's1ms minimum. This exercises the probe transport and emulator integration; it does
not validate silicon timing or the unknown TOP=0 outcome.

The [retained verification summary](../../reports/timer0-probe-20261024.json)
records toolchain, firmware/dependency/runtime hashes, the complete JS library
source identities, generated CPU WASM/manifest hashes and control results.
As a negative control, running the verifier with `--source` set to the original
pin-map source from commit `28aba01` fails before external stimulation:
TCNT0=112 instead of0, because each serialized bit clocks T0. The default source
uses PB4 for serialization and PB2 exclusively for the generator input.

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

The decoder accepts `--source FILE` to identify an alternate firmware source;
the verifier forwards its actual build source, so decoded provenance matches it.
The decoder checks sync, checksum, record order, pulse counts and scheduled-write
markers. It preserves counter/flag/output observations without comparing them
to a guessed TOP=0 model. Add measured conditions and instrument settings under
`measurements`; the JSON configuration embeds the trace schema. Synthetic
decoder checks must use `--capture-kind synthetic` and receive a different
status, so they cannot silently become hardware evidence.

```text
python web-player/native/peripherals/timer0-top-zero-probe-test.py
```

These five protocol tests cover arbitrary observed counter bytes, checksum
corruption, dropped pulse records, truncated captures and alternate-source
provenance. They supply no
physical Timer0 results. A future implementation must cite the actual observed
capture, check repeatability from reset, reconcile the two controls and preserve
any silicon-revision differences before replacing the existing fault.
