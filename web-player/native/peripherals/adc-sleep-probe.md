# Pending hardware probe: ADC sleep entry with ADIE clear

Status: **pending hardware**. These four source-only controls isolate whether
ADIE gates the automatic ADC start on sleep entry, or only its completion
interrupt. They do not select a silicon interpretation. The descriptor retains
`expectedSiliconTrace:null`; synthetic execution checks the current software
fixture and wire transport only. No hardware has been programmed or measured.
This fixture targets ATtiny13A, not the MH-ET LIVE Tiny88 board.

## Why acquire this separately

[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
sections 7.1.1/7.1.2, pages 36–37, describe automatic conversion when an enabled
ADC enters Idle or ADC Noise Reduction. Section 14.7, page 94, explicitly
requires single-conversion mode and the ADC completion interrupt enabled for
its noise-canceler procedure. The mode descriptions do not settle what happens
with ADIE=0. [AN2537/AVR125 section 1.6](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ApplicationNotes/ApplicationNotes/00002537A.pdf),
[AN2538/AVR126 section 1.6](https://www.microchip.com/content/dam/mchp/documents/OTH/ApplicationNotes/ApplicationNotes/AN2538-ADC-of-megaAVR-in-SingleEnded-Mode-00002538A.pdf)
and [original ATtiny13 section 14.7](https://ww1.microchip.com/downloads/en/DeviceDoc/doc2535.pdf)
repeat the interrupt-enabled procedure. They do not establish ADIE=0 behavior.
Retain this as an unresolved acquisition question, not a proven emulator bug.

The independent wake is supported by DS40002307A Table 7-1, page 36, and section
8.4, pages 44–45: the watchdog has its own oscillator and an interrupt mode
usable for sleep wake. Section 8.5.2/Table 8-2, pages 48–49, defines WDTIE=1,
WDE=0 and the 2K watchdog interval, typically 16 ms at 5 V. It is not an accurate
time reference. Section 14.12.2 documents ADIF clearing when the ADC interrupt
vector executes; therefore an ADC ISR's ADIF=0 is not evidence of no conversion.
Use the pinned [instruction manual](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
for SLEEP, SEI and interrupt return semantics. In particular, the SLEEP directly
after SEI executes before an interrupt can be accepted.

## Four paired controls

| Profile | MCUCR mode | ADIE |
|---|---|---|
| `idle-adie0` | Idle | 0 |
| `idle-adie1` | Idle | 1 |
| `noise-reduction-adie0` | ADC Noise Reduction | 0 |
| `noise-reduction-adie1` | ADC Noise Reduction | 1 |

All builds have ADEN=1, ADATE=0, ADSC=0, ADC1/PB2, VCC reference, right-adjusted
result and ADC /64. Firmware never sets ADSC. The first conversion, if any, is
the observation under test. Do not insert a manual warm-up conversion. ADEN is
already enabled during the two pre-sleep records, allowing over 400 us before
sleep with the declared clock. This is a fixture delay, not reference calibration.
PRADC=0; Timer0, comparator and other interrupt sources are disabled. BOD is
disabled by the declared fuses. No voltage/reference changes occur in a trial.

There is exactly one SLEEP per reset. WDT is armed just before SEI/SLEEP. If ADC
wakes the CPU first, main clears SE and waits **awake** for the watchdog; it
does not accidentally request a second sleep-entry conversion. The watchdog
ISR snapshots the ADC and disables WDT. All post-observation records are sent
with interrupts disabled. An unexpected vector traps without a completed
acquisition, rather than fabricating evidence.

At 8 MHz and /64 the ADC clock is 125 kHz; a 25-clock first conversion takes
about 200 us plus its start alignment, far shorter than the nominal watchdog
interval. Preserve measured clock and wake intervals. A missing watchdog
record or a watchdog interval too short to contain the conversion invalidates
the acquisition; it does not resolve the ADIE question.

## Wiring and acquisition

Use the same physical pin roles and electrical conditions as [adc-probe.md](adc-probe.md):
PB0 marker, PB1 trace clock, PB2/ADC1 analog input, PB3 continuous external
8 MHz CLKI, PB4 trace data, PB5 RESET. Use measured stable 5 V, common ground,
low/high fuses 70/ff, lock ff, and CLKPR=/1. The source uses
`../attiny13a-registers.generated.inc` from the pinned Microchip ATtiny_DFP
3.4.278 and the existing `probe-wire.inc`; there is no copied register map.

Hold ADC1 at a measured, low-impedance, nonzero in-range level, for example
0.2 VCC. Acquire all four profiles, then repeat at a second well-separated
constant level, for example 0.8 VCC. Repeat each build/level at least 32 times,
resetting between trials. Capture from before boot until the full final frame;
allow at least 50 ms initially and enlarge it if measured WDT behavior requires.
Do not infer a conversion merely from a retained zero or one raw result. Check
ADIF, ADSC, ISR count/order, the paired ADIE=1 control and the two input levels.
Do not substitute a nominal source/voltage or a programmed generator timestamp
for the acquired CLKI/ADC1/VCC waveform.

PB0 rises immediately before SEI/SLEEP and falls after the first ISR returns.
Its high interval witnesses sleep/first wake with instruction and interrupt
latency. It is not an exact conversion, ADIF or sampling timestamp. In ADIE=1
controls it can fall long before the watchdog; the CPU then waits awake.

CSV must contain `time_s,clock,data,clki,vcc,marker,adc1,reset`. Retain original
mixed-signal waveforms, their hashes, chip marking/revision, fuse readback,
measured clock, supply/temperature, stimulus levels/settling, acquisition
uncertainty and actual programmed-image/source/include hashes as described in
[hardware-probes.md](hardware-probes.md). Clock/data/CLKI/marker are digital;
VCC/ADC1/RESET are measured voltages. Keep the programmer's shared-pin drivers
released during acquisition. Building these sources does not program a chip.

## Raw wire-v2 record map

Each profile emits six consecutive records, sequence 0 through 5, probe ID 5.
All values below are bytes; data5 always identifies the record kind. The common
decoder preserves these bytes without deciding whether conversion happened.

| Sequence / kind | data0 | data1 | data2 | data3 | data4 |
|---|---|---|---|---|---|
| 0 planned controls | ADCSRA | sleep MCUCR | WDTCR | ADMUX | DIDR0 |
| 1 pre-sleep | ADCSRA | ADCL | ADCH | SREG | WDTCR |
| 2 ADC ISR | ADCSRA | ADCL | ADCH | entry SREG | ADC ISR count |
| 3 watchdog ISR | ADCSRA | ADCL | ADCH | entry SREG | WDT ISR count |
| 4 order / shutdown | ADC ISR order | WDT ISR order | total ISRs | final WDTCR | final MCUCR |
| 5 final frozen state | ADCSRA | ADCL | ADCH | SREG | total ISRs |

Sequence 1 is saved before watchdog arming/SEI; require ADSC=ADIF=ADATE=0,
ADEN=1, I=0, reset result=0 and WDT off. Sequence 2's first five bytes are all
zero if the ADC ISR was not entered; use its count, not the status byte alone.
Both ISR snapshots read ADCSRA first, then ADCL before ADCH. Their entry SREG
has I already cleared by interrupt entry. ADC ADIF is already acknowledged;
the ISR count and result retain that conversion evidence. Sequence 4 orders
the actual interrupts starting at 1 (0 means absent). Sequence 5 is frozen
after watchdog wake and CLI, before any result serialization. WDT must have
count 1, with no reset/restart or unexpected missing frame.

Two possible ADIE=0 outcomes remain open: a completed conversion can leave
ADIF=1 and a level-dependent raw result without an ADC ISR; no conversion can
leave ADIF clear and the reset result. Preserve any other observed state too,
including an incomplete conversion, unexpected order or inconclusive controls.
Do not coerce it to one of those candidates. ADIE=1 controls should establish
the acquisition can observe completion/ISR before using an ADIE=0 absence.

## Build, decode and software smoke

Use complete defines from `adc-sleep-probe.json`. For example:

```text
avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-e,__vectors -DPROBE_PROFILE_ID=1 -DPROBE_SLEEP_MODE=0 -DPROBE_ADIE=0 web-player/native/peripherals/adc-sleep-probe.S -o build/adc-sleep-probe.elf
avr-objdump -d build/adc-sleep-probe.elf
avr-size build/adc-sleep-probe.elf
avr-objcopy -O ihex -R .eeprom build/adc-sleep-probe.elf build/adc-sleep-probe.hex
python web-player/native/peripherals/hardware-probe-decode.py capture.csv --config web-player/native/peripherals/adc-sleep-probe.json --profile idle-adie0 --capture-kind hardware --measurements conditions.json -o decoded.json
node web-player/scripts/verify-adc-sleep-probe.mjs
```

The verifier reuses the prepared relocatable AVR GCC 7.3.0 assembler/toolchain
and Python; supply `--avr-bin DIR` / `--python FILE` when not found. It builds
all four actual images, checks 1024-byte Flash/zero data/BSS, executes generated
AVR→WASM with native peripherals and continuous supplied CLKI, and decodes all
24 wire records. It retains compiler listings, image/source/include/runtime/
translated hashes and raw synthetic records in ignored
`build/adc-sleep-probe-verification/`; `--out DIR` changes this location.
Maximum stack use is four bytes: either main→sender→byte, or watchdog interrupt
return plus saved SREG/r16. No heap or SRAM result buffer is used.
All four controls assembled to 424 bytes Flash and zero data/BSS with the
prepared AVR GCC 7.3.0; all four software smoke controls passed. This size and
software validation is not a silicon observation.

The verifier also runs **two separate synthetic host-injected positive controls**
using exactly the original ADIE=0 images, one per sleep mode. Only after the
firmware has entered its one SLEEP with PB0 high, a debugger write sets ADSC
once while keeping ADIE=0. The report retains the intervention timestamp and
before/written/after ADCSRA bytes. A later checkpoint verifies ADIF=1, ADSC=0
while the CPU is still asleep, without an ADC ISR or an early marker fall.
Each decoded positive-control JSON also retains this explicit synthetic
intervention/checkpoint metadata alongside its unchanged raw frame bytes.
The independent watchdog then wakes the CPU; both its ISR record and the final
record must retain ADIF=1 and raw result 204 under the declared ideal 1 V/5 V
software stimulus. Thus the actual firmware/encoder/decoder path can preserve
the alternative completed-conversion outcome without an ADC interrupt.

These controls are a debugger intervention, **not silicon behavior or evidence
that firmware sleep entry automatically starts an ADIE=0 conversion**. Firmware
still never writes ADSC, and its four source profiles are unchanged. The two
positive-control captures and their own `summary.json` are kept separately in
`build/adc-sleep-probe-verification/host-injected-positive-controls/`; the original
four-profile `summary.json` remains separate. Their images/translated modules
must match the corresponding unmodified controls. There are 12 additional raw
records in this explicitly synthetic cohort; none is a hardware observation.

The current software fixture predicts ADIE=0: no conversion/ADC ISR, watchdog
wake, ADIF clear, result zero; ADIE=1: ADC ISR then watchdog, acknowledged ADIF,
result 204 at ideal ADC1=1 V/VCC=5 V. Assertions intentionally identify these
as **current fixture predictions**, not hardware expectations. Smoke artifacts
retain transport/marker transitions only; they are not full mixed-signal
captures and cannot be relabeled as hardware evidence. A software pass resolves
neither ADIE=0 silicon behavior nor the separate aperture/ADIF questions.
