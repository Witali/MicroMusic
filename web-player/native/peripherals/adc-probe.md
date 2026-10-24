# Pending hardware probes: ADC aperture and ADIF bit operations

Status: **pending hardware**. `adc-probe.S` records raw observations; it does
not determine either unresolved silicon result. `adc-probe.json` specifies the
nine build profiles, wiring and record format with `expectedSiliconTrace:null`.
Neither source assembly nor synthetic decoding is a hardware measurement.

## Official conflicts and definitions

[Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
section 14.5, page 91, gives the first sample/hold at 14.5 ADC clocks; Table
14-1, page 93, gives 13.5. Both give a 25-clock first conversion. The ordinary
conversion control uses the documented 1.5-clock sample and 13-clock completion.

Section 14.12.2, page 99, warns about pending ADIF under ADCSRA read/modify/write
including SBI/CBI. Section 5.4, page 26, and section 20 note 2, page 165, instead
say these instructions affect only their selected bit, including flag registers.
The current emulator choices remain explicit until actual measurements or an
authoritative clarification resolve these contradictions.

Use the pinned [AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
sections 5.33, 5.60, 5.84, 5.90, 5.95 and 5.100 for CBI/IN/OUT/RJMP/SBI/SBRC.
The ATtiny13A instruction summary also specifies two clocks for SBI/CBI. Do not
use reduced-core cycle counts or silently substitute a newer manual revision.
Pinned document hashes are in `../../reports/attiny13a-instructions.json`.

The firmware includes `../attiny13a-registers.generated.inc`, generated from
Microchip ATtiny_DFP 3.4.278. Register addresses, bit positions and RAMEND come
from that include; no manually copied register map is needed.

## Wiring and conditions

| Pin | Connection |
|---|---|
| PB0 | Acquisition marker; rise immediately before measured ADSC OUT |
| PB1 | Serialized result clock, sampled on its rising edge |
| PB2 / ADC1 | External analog stimulus; digital input disabled |
| PB3 / CLKI | Stable external 8 MHz clock, captured with the marker |
| PB4 | Serialized result data |
| PB5 / RESET | Normal RESET role, retained |

Use measured stable 5 V, common ground, low/high fuses 70/ff and lock ff, with
CLKPR=/1. Match the clock/generator logic levels to VCC. Release programmer
drive on shared pins before acquisition. Record actual fuse readback, chip
marking/revision if available, supply, temperature and clock; nominal settings
are not measurements. ADC uses /64, or 125 kHz with the specified clock, and
VCC as reference. Do not switch reference or channel during a trial.
CLKI must be stable before RESET release and remain running through the last
record. Retain its actual waveform rather than substituting the nominal rate.

Firmware disables interrupts, watchdog, Timer0, comparator and auto-triggering.
PB1/PB4 transport does not run during a conversion. The ADC is disabled for
32008 CPU clocks before each trial, about 4 ms at 8 MHz; the external source
must return to the declared baseline before the next PB0 rise. A warmed control
adds an unmeasured initialization conversion with the baseline held steady.
The default build performs two measured trials and then halts in a loop. The
warmup is not a measured trial. Re-run from RESET for each acquisition; use
`PROBE_TRIALS` in 1..255 when more trials per setting are needed.

For the aperture profiles, use an external low-impedance analog step between
well-separated in-range levels, for example 0.2 VCC and 0.8 VCC. Sweep its delay
from PB0 rising and capture the actual voltage and settling at PB2. Reverse the
step as well. Preserve constant-level and early/late-step controls, and repeat
each setting at least 32 times. Do not replace measured analog settling with
the generator's programmed delay or its digital trigger timestamp.

## First and normal conversion profiles

`PROBE_MODE=0` starts the measured conversion after ADEN was cleared.
`PROBE_MODE=1` first completes an unmeasured conversion, retains ADEN and starts
the measured normal conversion. The actual measured start sequence is:

```asm
 in r8,ADCSRA
 out PORTB,r19                 /* PB0 rises; trace clock/data low. */
 out ADCSRA,r16                /* ADEN+ADSC, ADIF W1C, /64. */
adc_probe_measured_wait:
 in r18,ADCSRA
 sbrc r18,ADSC
 rjmp adc_probe_measured_wait
 out PORTB,r20                 /* PB0 falls after a successful poll. */
```

The unsuccessful poll loop takes four CPU clocks. The successful IN, skipped
one-word RJMP and final OUT add a bounded marker latency. Decode a **completion
interval** from the actual instruction listing and measured clock; allow the
uncharacterized within-instruction read/output phase, pad delay and instrument
uncertainty. A conservative initial bound is completion within the preceding
eight CPU clocks before the falling marker, enlarged by measured pad/instrument
uncertainty. Do not identify the falling marker with an exact ADIF transition.

Scan where raw conversion codes change between the two plateau distributions.
Infer an aperture interval using the actual analog transition/settling and the
completion interval. Comparing aperture to completion avoids assuming the
hidden prescaler's start phase. The two first-conversion interpretations imply
completion minus aperture of 11.5 or 10.5 ADC clocks; the normal control implies
11.5. Their separation is one ADC period, 8 us for this fixture. These are
candidate interpretations, never a supplied observed waveform. Report an
inconclusive result if settling, noise, polling or instrument uncertainty cannot
exclude one candidate. Do not discard the first conversion under test.

## ADIF profiles

`PROBE_MODE=2` performs one single conversion at a constant ADC1 voltage. It
waits for ADSC=0, snapshots ADCSRA, executes exactly one selected operation and
immediately snapshots ADCSRA again. ADATE=0 and SREG.I=0; no ISR may acknowledge
ADIF and no new conversion runs between these observations. The CBI ADIE
profile sets ADIE with the complete start byte before conversion, not with SBI.

| PROBE_ADIF_OPERATION | Operation | Record kind |
|---|---|---|
| 0 | Two NOPs, no write | 3, control |
| 1 | SBI ADCSRA,ADIE | 2, unknown ADIF result |
| 2 | CBI ADCSRA,ADIE, initially set | 2, unknown ADIF result |
| 3 | CBI ADCSRA,ADPS0, already zero at /64 | 2, unknown ADIF result |
| 4 | Full OUT preserving ADEN and /64, ADIF=0 | 3, preserve-flag control |
| 5 | Same full OUT with ADIF=1 | 3, W1C-clear control |
| 6 | Explicit IN/ORI ADIE/OUT retaining read-one ADIF | 3, byte-RMW control |

Reject a trial as invalid acquisition if the before snapshot lacks ADIF or has
ADSC/ADATE set, or if SREG.I is set. Inspect all raw bits, including ADEN,
prescaler and ADIE; do not reduce the evidence to one Boolean. No-write and
whole-byte controls distinguish a failed setup/transport from the disputed
SBI/CBI behavior. Serialization completes before the next independent trial.

## Build and records

Choose the complete defines of one JSON profile, including required
`PROBE_PROFILE_ID`. `PROBE_MODE` selects first/normal/ADIF; `PROBE_ADIF_OPERATION`
selects the compile-time ADIF operation. `PROBE_TRIALS` defaults to 2.

If changing PROBE_TRIALS, retain a matching acquisition descriptor with its
defines and expectedRecords updated to 1 + PROBE_TRIALS; the canonical JSON
describes the default two-trial builds. For example:

```text
avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-e,__vectors -DPROBE_PROFILE_ID=1 -DPROBE_TRIALS=2 -DPROBE_MODE=0 web-player/native/peripherals/adc-probe.S -o build/adc-probe.elf
avr-objdump -d build/adc-probe.elf
avr-size build/adc-probe.elf
avr-objcopy -O ihex -R .eeprom build/adc-probe.elf build/adc-probe.hex
```

The shared `probe-wire.inc` emits sync a5 5a, 11 payload bytes and an XOR
checksum, MSB first. Payload is version2, probeId3, profileId, sequence low/high,
then six data bytes. Boot sequence is zero; measured trial sequences start at
one and finish at PROBE_TRIALS, without gaps. The default capture has exactly
three records: boot plus two trials. Keep the full capture from boot onward.

| Data | Conversion / ADIF record | Boot record, kind0 |
|---|---|---|
| 0 | Raw ADCL | Planned ADCSRA start byte |
| 1 | Raw ADCH | ADMUX |
| 2 | ADCSRA before start / operation | ADCSRB |
| 3 | ADCSRA after completion / operation | DIDR0 |
| 4 | Saved SREG | Saved SREG |
| 5 | Kind1 conversion, kind2 ADIF test, kind3 ADIF control | Kind0 boot |

ADCL is always read before ADCH, after the status snapshots. Observations remain
in registers while the shared encoder clobbers r12/r17/r18/SREG; r16 is preserved.
No EEPROM writes, heap or static SRAM buffer are needed. Check all nine builds
against 1024-byte Flash and the 64-byte SRAM budget before physical use.
All nine canonical profiles assemble with AVR GCC 7.3.0: 278--286 bytes Flash,
zero data/BSS and four stack bytes in the shared encoder. These size/syntax
checks establish neither ADC sample timing nor ADIF behavior on hardware.

The [shared decoder](hardware-probes.md) retains raw register bytes, sequence/checksum validation,
source/include/capture hashes and the referenced raw mixed-signal
capture. `frameEndSeconds` is a transport timestamp only. Store completion and
aperture **intervals**, not a fabricated exact `sampleTime`. Mark synthetic
decoder fixtures separately from `observed-hardware` and preserve inconclusive
and silicon-revision-dependent outcomes. This source does not close stage 3's
hardware-validation acceptance or change an emulator default.
Retain the actual programmed-image hash with the lab conditions separately.

CSV must include `time_s,clock,data,clki,vcc,marker,adc1,reset`. Clock/data/CLKI/
marker are digital 0/1; VCC, ADC1 and RESET are actual measured voltages, not
nominal values or digital surrogates. Preserve the raw acquisition too. The
shared decoder retains the raw waveform reference/hash and six-byte record; it does
not determine the ADC aperture or the ADIF outcome.
