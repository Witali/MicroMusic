# Pending hardware probe: ATtiny13A CLKPR switching

Status: **pending hardware**. The firmware and JSON describe a reproducible
measurement, with `expectedSiliconTrace: null`. No measured transition waveform
or exact internal bus phase is supplied. Software compilation and synthetic
transport checks cannot establish a silicon result.

Official sources: [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections6.3–6.4 (printed pp32–35), section11.7.2 (pp70–71), and the pinned
[Microchip ATtiny DFP3.4.278](https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack).
The source includes `../attiny13a-registers.generated.inc`, derived from those
unmodified manufacturer definitions; there is no hand-copied register map.

## What is observed

Timer0 uses **CTC WGM2**, OCR0A=0, CS=/1 and toggle OC0A. Its documented output
frequency is clkI/O divided by two: each observed OC0A transition witnesses one
synchronous clock tick. This is separate from the unresolved phase-correct
WGM5/TOP0 experiment. The observer is warmed up before the first frame; no
Timer0 register is changed in the measured window.

The source clock and the divided clock must be captured independently. CLKI
is not the CPU clock when CLKPR differs from zero. Section6.3.1 gives the
T1+T2..T1+2*T2 switching interval and two active edges, while explicitly leaving
the ripple phase unpredictable. The probe does not choose a universal point
within that interval. CLKPCE must be unlocked and CLKPS written within four
CPU cycles, with interrupts disabled.

## Wiring and acquisition

Use a stable, measured supply within the device operating range and an external
1MHz source at0..VCC, approximately50percent duty, with common ground. Keep
CLKI present before RESET release and continuously running through the write
and capture. Check the actual source waveform against section18.4.2/Table18-3,
including rise/fall and high/low times. This probe does not characterize source
stops, frequency steps or an internal RC oscillator's calibration.

| Pin | Role |
| --- | --- |
| PB0 / OC0A | Continuous divided-clock witness from CTC |
| PB1 | Low-high-low marker around the target instruction slot |
| PB2 | Serial trace clock, idle low |
| PB3 / CLKI | Continuous external1MHz source, captured separately |
| PB4 | Serial trace data, sampled on PB2 rising edges |
| PB5 / RESET | Normal external RESET role |

For PDIP8/SOIC8 these are physical pins5,6,7,2,3,1 respectively; confirm the
package before wiring. PB2 is also T0, but Timer0 here selects its **internal**
CS=/1 clock, so trace serialization is not its clock source. PB3 is never a
serial output. Release any programmer drive before acquisition.

Use low/high/lock fuse readback70/ff/ff: CKSEL00, SUT00, CKDIV8 unprogrammed,
WDTON unprogrammed, RESET enabled and debugWIRE disabled. These are fixture
choices, not default chip fuses. Hold supply stable before release; SUT00 is
not a substitute for power-startup characterization. The firmware separately
sets the requested initial CLKPR; it does not rewrite fuses or OSCCAL.

Start acquisition before RESET release. Capture the complete sequence0 frame,
marker pulse, nearby uninterrupted CLKI/OC0A edges, and complete sequence1
frame. Record enough old/new OC0A intervals to establish steady divisors. At
1MHz, one source period is1microsecond. Choose and document sample rate,
timebase error, threshold, probe loading and channel skew; a nominal100MS/s
digital acquisition gives10ns sample granularity, not10ns total accuracy.
The /256 profiles serialize slowly and may require a capture lasting seconds;
do not stop at the marker or truncate the second frame.

## Profiles and firmware sequence

Build every JSON profile separately and repeat each from reset. The12 profiles
cover /1→/2,/8,/256; their reverses; /2↔/8; /8→/8; and no-write, no-unlock,
expired-unlock controls. `PROBE_INITIAL_DIV` and `PROBE_FINAL_DIV` are exponent
codes0..8, not literal divisors. `PROBE_PROFILE_ID` is mandatory and identifies
the build in each frame. `PROBE_WRITE_KIND` selects:

| Value | Instruction sequence |
| --- | --- |
|0|Unlock OUT, marker-high OUT, target CLKPR OUT, marker-low OUT|
|1|NOP, marker-high OUT, NOP, marker-low OUT; no measured CLKPR write|
|2|NOP, marker-high OUT, target CLKPR OUT without unlock, marker-low OUT|
|3|Unlock OUT, six NOPs, marker-high OUT, target OUT, marker-low OUT|

Register operands are loaded before the measurement. All marker writes use
single-instruction PINB toggle of PB1; OC0B is disconnected. The kind0 target
remains within the protected window. Kind3 deliberately expires that window
before the marker. Negative controls request /8 but should retain their
initial register selection; preserve an unexpected physical observation for
investigation rather than substituting an emulator waveform.

Sequence0 is a pre/boot register snapshot after settling. After its complete
serialization,16NOPs precede the measurement. Sequence1 follows32NOPs and a
post snapshot. Timer0 and CLKI continue through both frames and the final loop.
Serialization and readback are outside the measured instruction window.

The marker is a **bracket**, not an exact CLKPR bus-write timestamp. Output-pad
propagation, timer output latency, channel skew and unspecified internal phase
remain in the observation. In particular, the marker pulse width need not be
one already-settled new CPU period. Register readback confirms the accepted
code; it does not date the waveform transition. Compare raw edge sequences
and stated uncertainty with the documented interval before fitting any model.
Repeated observations on one chip do not establish universal ripple phase.

## Build and provenance

The common transport is `probe-wire.inc`; retain its exact revision with this
source. It sends synca55a, then11payload bytes and their XOR checksum,14bytes
total, MSB-first. Payload order is version2, probeId1, profileId, sequence low,
sequence high, then these six raw data bytes:

| Byte/register | Field |
| --- | --- |
| data0/r6 | writeKind |
| data1/r7 | initialDivCode |
| data2/r8 | requestedDivCode |
| data3/r9 | clkprReadback |
| data4/r10 | tccr0a |
| data5/r11 | tccr0b |

Only sequence0 and1 are emitted. Frame end times locate transport activity,
not CLKPR events. Save an edge/sample CSV with columns
`time_s,clock,data,clki,vcc,oc0a,marker,reset` and original instrument files. Keep
monotonic finite timestamps. Clock/data/clki/oc0a/marker are binary digital
levels; reset/vcc contain actual measured volts, not logic-threshold labels.
If analog and digital channels come from separate instruments, retain their
common trigger/time reference and synchronization uncertainty. A decoder must preserve
the actual waveform and identify synthetic tests separately from hardware
captures; there is no expected silicon transition trace to generate.

From the repository root, this builds the /1→/2 profile using a prepared AVR
toolchain (all outputs under ignored `build/`):

```text
avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-e,__vectors -DPROBE_PROFILE_ID=1 -DPROBE_INITIAL_DIV=0 -DPROBE_FINAL_DIV=1 -DPROBE_WRITE_KIND=0 web-player/native/peripherals/clkpr-probe.S -o build/clkpr-probe.elf
avr-size build/clkpr-probe.elf
avr-objcopy -O ihex -R .eeprom build/clkpr-probe.elf build/clkpr-probe.hex
```

For another profile use every `defines` entry from JSON. Record compiler/binutils
versions, exact commands/defines, device marking/revision, package, actual fuse
readback, measured VCC/temperature/source frequency and instrument uncertainty.
Retain SHA256 for this source, JSON, `probe-wire.inc`, generated definitions,
manufacturer provenance and original headers, ELF/programmed image, and every
raw capture. Never reuse an old-pin-map or differently configured capture under
the current hashes. Keep hardware acceptance open until real traces exist.

On2026-10-24 all12 configurations assembled with prepared AVR GCC7.3.0 and the
shared wire-v2 include:602bytes Flash for eleven profiles,614bytes for expired
unlock, zero data/BSS. Generated ELF files remain under ignored
`build/clkpr-probe-check/`. These size/syntax checks provide no hardware trace.

See [shared transport and decoder](hardware-probes.md) for capture identity,
condition metadata, strict framing and trace-clock idle loading.
