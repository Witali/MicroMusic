# Pending hardware probe: physical RESET and CLKI

Status: **pending hardware**. `reset-probe.S` records reset causes and emits an
observable boot marker/frame. `reset-probe.json` defines reproducible profiles
and acquisition cases; `expectedSiliconTrace` is null. No simulated waveform is
an observed chip response. Loading this firmware does not implement a virtual
programmer; ISP/HVSP remain outside the emulator's scope.

## Manufacturer reference and measurement boundary

Reference: Microchip [ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf):
sections 8.1–8.2 and 8.5.1, printed pages 41–43/48; 6.2.1–6.2.2 and 6.4,
pages 30–34; 18.5/Table 18-4, page 126. External CLKI is section 6.2.1;
6.2.2 describes the internal calibrated RC source. Register/bit/memory symbols
use the generated view of the pinned official Microchip device pack.

Reset restores port state independently of a running clock. Sufficient RESET
pulses work without CLKI; shorter pulses are not guaranteed. Published reset
threshold/width limits do not specify an exact receiver transfer function.
External startup combines 6+14 source CK with SUT-selected independent watchdog
timeouts of 0, 512 or 8192 pulses. The 4/64 ms labels are typical, not exact
delays. CKDIV8 sets initial CLKPR to divide by eight when programmed. MCUSR is
a bitmask of causes and is saved before clearing.

Those facts do not supply exact analog assertion, release or CPU-start
timestamps. A threshold sweep cannot uniquely separate receiver hysteresis,
filtering, propagation, synchronizers, startup sequencing and output-pad delay.
CLKI hold/resume experiments also require the datasheet's frequency-change
cautions; observations after a hot change are not automatically qualified.

## Wiring

Use stable measured VCC, shared ground, a 1 MHz external clock with measured
500 ns high/low phases, and a RESET generator whose levels follow VCC. Keep
PB5's reset role enabled, DWEN/WDTON unprogrammed, and record fuse/lock readback.
Check the physical package pinout before connecting by PB name.

| Pad | Role |
| --- | --- |
| PB0 | Running/HiZ witness; **external 47 kΩ pulldown to GND** |
| PB1 | Heartbeat after the complete boot frame |
| PB2 | Shared wire-v2 trace clock, initially low |
| PB3 | External CLKI input, never a firmware output |
| PB4 | Shared wire-v2 trace data |
| PB5 | Analog RESET drive/observation; normal reset role |

The pulldown makes a reset/high-impedance PB0 tend low instead of floating.
Its measured fall includes the resistor, pad/probe capacitance, loading and
analyzer threshold. Record those conditions; a falling digital marker is not
the exact internal assertion timestamp. Use high-impedance measurement inputs.
Release programmer drives on shared pins before acquiring the experiment.

At each reset, the handler first reads MCUSR into r6. It then sets PB0's DDR
while its PORT latch is still reset-low, followed by PORT-high. This **DDR-first**
sequence produces a driven marker, not an early pull-up through an input pin.
The rising marker follows vector RJMP, MCUSR read and DDR setup instructions;
it is not the first executing CPU clock. Firmware then initializes SP, clears
saved reset causes in MCUSR, disables WDT/interrupt sources/Timer0/ADC/comparator,
and configures the remaining output pins. It never writes CLKPR or OSCCAL.

## Profiles and acquisition cases

| Profile | ID | Low fuse | SUT | Initial division |
| --- | --- | --- | --- | --- |
| `sut00-clki-div1` | 1 | 0x70 | 00 | 1 |
| `sut01-clki-div1` | 2 | 0x74 | 01 | 1 |
| `sut10-clki-div1` | 3 | 0x78 | 10 | 1 |
| `sut00-clki-div8` | 4 | 0x60 | 00 | 8 |

High fuse/lock are 0xff. The default is the first profile. The /8 control uses
the chip's CKDIV8 initialization, without overriding it in firmware. SUT00 is
tested with supply already stable; it is not evidence for arbitrary power ramps.
Repeat from a known initialized device and retain the actual operating conditions.

1. With continuous CLKI, establish the **10 µs low RESET control** at full
   amplitude. Capture before assertion through the complete new boot frame and
   several heartbeat transitions. Repeat for every fuse profile.
2. Sweep low widths **0.1, 0.2, 0.4, 0.7, 2, 2.5 and 5 µs**, recording the actual
   analog threshold crossings, slew and phase relative to CLKI. Treat each as
   an observation, not an assumed accepted/rejected pulse. Vary CLK phase and
   repeat independently after recovery.
3. Sweep assertion/release amplitudes with measured VCC and controlled edges.
   Retain analog RESET/VCC, not just a thresholded digital trace. These sweeps
   cannot by themselves identify the internal reset circuit or individual delays.
4. Reassert RESET during recovery, then separately during boot serialization.
   Preserve partial frames and marker intervals. Do not infer that a missing
   complete frame means reset never occurred.
5. Hold CLKI low and high in separate runs; assert/release RESET during each
   hold. Keep RESET asserted during the deliberate clock transition where
   possible, then resume the measured source with controlled phase. Capture the
   whole hold/resume sequence. Count actual supplied CK; no average period is
   substituted for missing edges. Short-pulse/hot-resume variants are exploratory.

For independent trials allow a complete frame and heartbeat first. For recovery
and reassertion cases use a recorded schedule that intentionally interrupts it.
The waveform, not an assumed 4/64 ms deadline, determines the observed interval.

## Boot record and heartbeat

`probe-wire.inc` is the shared transport. The caller defines clock bit PORTB2
and data bit PORTB4. Each frame is 14 bytes: sync a5 5a, 11 payload bytes, XOR
checksum; MSB first, data sampled at PB2 rising. This probe uses **wire version
2**, distinct from the older Timer0-specific wire-v1 format.

Payload order is version, probeId, profileId, sequence low/high, then six bytes:

| Register | Field | Meaning |
| --- | --- | --- |
| r6 | `mcusr` | Raw cause bitmask saved by the first handler instruction |
| r7 | `clkpr` | Read-only initial clock-prescaler register |
| r8 | `osccal` | Read-only reset-loaded calibration byte |
| r9 | `ddrb` | Output configuration at the boot snapshot |
| r10 | `portb` | PORT latch snapshot before serialization |
| r11 | `kind` | 0: boot after reset |

Probe ID is 2; profile ID comes from `PROBE_PROFILE_ID`. **Every reset emits
sequence zero**, using cleared r2/r3 rather than retained SRAM. Multiple resets
therefore legitimately repeat sequence zero. Wire clobbers r12/r17/r18/SREG
and preserves r16. The six observations precede serialization and are not
measurements at frame end. A reset inside a frame can leave an incomplete record.
The shared decoder is strict by default. For an intentional interrupted capture,
its explicit `--allow-reset-fragments` mode preserves marked unframed ranges;
it must not silently discard them or treat repeated sequence zero as packet loss.

Only after the frame returns does PB1 toggle in a fixed software loop. Its
steady toggle interval is 1029 CPU cycles from the explicit instruction loop;
this is a firmware witness, not a calibrated oscillator or recovery timer.
A held CLKI also holds this witness. The initial PB1 edge follows serialization,
so it cannot timestamp CPU startup independently of the marker/prologue.

## Build and retained evidence

From the repository root, with the shared `probe-wire.inc` present:

```text
avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-e,__vectors -DPROBE_PROFILE_ID=1 web-player/native/peripherals/reset-probe.S -o build/reset-probe.elf
avr-size build/reset-probe.elf
avr-objcopy -O ihex -R .eeprom build/reset-probe.elf build/reset-probe.hex
```

Select the matching JSON profile's define and fuses, program with the lab's
existing hardware tools, and verify readback. Put outputs under ignored `build/`
or an external lab directory. Compilation validates syntax/size, not a reset
result. No binary or fabricated expected waveform is retained as source.

All four profiles assemble with the repository's AVR GCC 7.3.0 toolchain and
`-Wall -Wextra -Werror`: 204 bytes Flash, zero data/BSS. The shared transport
uses at most two return addresses (four SRAM stack bytes). Disassembly confirms
MCUSR-first, DDR-before-PORT marker setup and no CLKPR/OSCCAL write. This is
build evidence only; no hardware trace has been collected.

Preserve original analog **RESET, VCC and PB0**, and digital **CLKI, PB0, PB1,
PB2, PB4** captures, including pretrigger and incomplete frames. Record chip
marking/revision if known, temperature, fuse/lock readback, amplitudes/impedance,
actual pulse timing, RC loading, instrument settings/thresholds and source,
configuration, shared-wire and programmed-image SHA-256. Decoded records must
remain linked to that raw evidence. No hardware outcome is supplied by this probe.

CSV columns are `time_s,clock,data,clki,vcc,running,heartbeat,reset`.
`reset` and `vcc` contain measured numeric **volts**, not inferred digital levels;
clock/data/CLKI/running/heartbeat are 0/1 digital observations with recorded
instrument thresholds. Keep the original analog marker recording separately.

See [shared transport and decoder](hardware-probes.md) for commands, condition
metadata and explicit interrupted-frame recovery. Record the trace-clock
pulldown/loading too, so RESET/HiZ intervals have a defined idle level.
