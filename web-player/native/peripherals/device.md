# ATtiny13A C board scheduler

`device.c` binds the standalone Timer0, GPIO, sleep, watchdog, NVM, ADC and
comparator modules to one allocation-free device per WASM instance. CPU state
is supplied through `data[160]`, `flash[1024]` and `eeprom[64]`; PC, registers,
stack, SREG.I, instruction effects and interrupt entry remain the CPU's job.
The module has no JavaScript imports, callbacks or per-clock host calls.

Official references are [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
especially sections6.3–6.4,7.1–7.5,9–14,16–17 and the register summary, and the
[AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/devicedoc/AVR-Instruction-Set-Manual-DS40002198A.pdf).
The individual modules' documentation continues to define their analog/timing
parameters and explicitly unsupported cases.

## Public contract

Configure numeric keys in `device.h` before `device_init`. Configuration changes
prepare the next initialization; they do not alter a running board. Defaults
choose9.6MHz oscillator, nominal128kHz watchdog, fuses7a/ff and the documented
Flash maximum duration. The caller must explicitly configure SPM command cycles
for commands without a page-program wait; zero produces a timing fault instead
of inventing an instruction duration. Supply/bandgap, comparator delays, first
ADC sample ambiguity and oscillator startup are explicit fixture choices.

`device_read(io)` and `device_write(io,value,mask)` operate at the current bus
instant. Byte stores use mask255; SBI/CBI preserve their one-bit mask. PINB
toggles only selected bits; NVM/FOC strobes do not replay other old bits; W1C
flags acknowledge only written bits. ADCL/ADCH side effects happen on actual
bus reads. Canonical data mirrors are updated directly and never acquire ADC
result locks just by being mirrored. SREG/SPL are caller-owned passthroughs.

ADCSRA follows section14.12.2's explicit warning that SBI/CBI may clear an
already-set ADIF through read/modify/write. The same data sheet's register
summary note2 says that this chip's SBI/CBI affect only the selected bit even
with status flags. That is an unresolved official-document conflict. This
board's ADCSRA choice is explicit and tested; a silicon trace is still needed.

All IRQ requests become vector-word bits1..9. `device_next_irq` chooses the
lowest word and `device_ack_irq` routes acknowledgment to the owner. EEPROM
ready remains a level. The CPU decides global enable, SEI/RETI delay, stack
effects and four-cycle entry. Wakeup uses enabled live requests, then the CPU
arbitrates again after startup; an old INT0 wake request is not forced into an
ISR after the physical level has disappeared.

`device_control(1,...)` enters sleep after the CPU charges SLEEP's one cycle;
command3 performs WDR after its cycle. Command2 executes SPM at its instruction
effect instant and returns any configured command cycles to charge. Page erase
and write halt the CPU until asynchronous NVM completion. `device_lpm` handles
the fuse/lock window before ordinary Flash. After a Flash generation change,
the CPU must invalidate/retranslate dirty pages before fetching again.

## Time authority and ordering

`device_base_half()` is a monotonic physical timeline in half oscillator
periods, independent of CLKPR. `device_virtual_half()` is a monotonic nominal
divided-clock timeline used by the component APIs. It continues as a time
coordinate during sleep while those APIs gate their actual clocks. Timer0's
prescaler and GPIO synchronizers freeze when clkI/O stops; ADC Noise Reduction
retains the ADC clock. Power reduction also gates the relevant modules.

This paragraph describes the default fixed-frequency contract. Supplying an
explicit OSCCAL table selects the separate fixed1ps contract, `_ps` input/output
and deadline APIs; legacy timed accessors then fail rather than changing units.
See [runtime OSCCAL and physical time](device-osccal.md).

Pin voltage propagation uses the comparator's stored PB0..PB5 voltages as its
existing resolved-input state. Only changed voltages are injected, in ascending
pin order; unchanged PB5 still settles events at the end of the board operation.
Explicit analog overrides, GPIO levels, VCC changes and reset all use this same
path, including PB3/ADC3 while CLKI owns the pin. No additional cache or reset
invalidation protocol is needed. Skipped unchanged pin/flag notifications also
avoid their repeated module advances. The analog scheduler still processes all
due events at an already-serviced timestamp: a mutation can have scheduled new
zero-delay propagation. Held trigger flags need no new ADC notification;
ADTS/ADATE register writes keep their own edge handling. Sampling still precedes
voltage mutation at equal time.

Nanoseconds and watchdog pulses are rational conversions from elapsed
`base_half` with retained remainders. They are never derived from executed
instruction count. EEPROM/Flash programming and the watchdog therefore keep
their wall-time behavior across CLKPR changes and CPU sleep. The host need not
send oscillator pulses individually.

CLKPR keeps its protected four-cycle write window, including nonextension by
an attempted CLKPCE rewrite. A selected divisor is readable immediately, but
the actual waveform uses one old period for its next active edge, then one new
period for its second edge. This explicitly selects the T1+T2 lower bound from
section6.3.1's T1+T2..T1+2*T2 interval. The phase of real silicon's ripple divider
is not claimed to be predictable. `device_clkpr_divisor()` returns the current
actual waveform divisor. Generated blocks stop before its scheduled transition.

`device_advance(n)` targets the requested number of virtual CPU periods, so it
crosses a pending divisor change correctly. It visits the minimum deadline of
GPIO settling, timer/analog events, protection windows, asynchronous programming,
watchdog, wakeup and queued inputs. Stable spans skip directly between events.
`device_next_cpu_event` returns a conservative CPU-cycle **distance** rounded
down. Blocks must end strictly before it. Rounding up could admit a physical
endpoint tie (two9MHz cycles and RESET both at222223ps), cancelling a whole
resumable block or committing an ordinary block before the individual
instruction effects. Single instructions still advance through an event
internally. This event bound differs from the separate rounded-up half-cycle
observation-deadline conversion.

At an event boundary, GPIO samples previous pin values, analog samples previous
voltages, Timer0 counts, NVM/watchdog/sleep advance, and timer outputs propagate
through physical GPIO. ADC auto triggers use original interrupt flag levels,
independent of their interrupt masks: comparator, INT0, compareA, overflow,
compareB and PCINT all connect in C. External digital/analog injections at that
same timestamp follow sampling. New requests then start wakeup and register
mirrors update. This ordering prevents one host block from collapsing distinct
peripheral events into a single late mutation.

Digital injections provide resolved external drivers and analog injections
provide explicit PB-pin voltages. Pins without an explicit analog fixture track
their resolved digital level at0/VCC, including actual PWM output pins. Explicit
analog values do not invent digital thresholds; inject the digital fixture too
when its sampled logic level matters. Inputs must be queued chronologically.
Current-time inputs apply immediately after sampling already done at that time.

`device_wait_until(base_half_deadline)` advances halted hardware to wake/program
completion, reset or the caller deadline. It never waits in JavaScript or spins
an unbounded sleep instruction. Its return value counts complete virtual CPU
periods; `base_half` remains authoritative at an endpoint between clock edges.

## Physical output buffering

The board captures physical six-pin levels, drive masks, pullups, floating pins
and contention into1024 fixed16-byte records. Unlike Timer0 OC latch snapshots,
these records include DDRB and port-mux effects. Timestamps use `base_half`.
Same-time mutations coalesce. `device_pin_events` exposes a contiguous host ring
batch and `device_consume_pin_events` releases it without allocation or copying.
Native PCM has a separate1024-record ring, selected by mono/stereo pin levels;
host consume/clear cannot steal its transitions. The default host mask63 retains
the former full trace and legacy audio discard. Explicit masks and retained
history are independent of live GPIO and all internal pin consumers. See the
[pin observation contract](../devices/attiny13a/pin-observation.md).
No output transition invokes JavaScript.

Buffer overflow latches `DEVICE_FAULT_OUTPUT_OVERFLOW` and increments a visible
host drop counter; private PCM has its own counter. Callers must drain explicitly
retained host history during bounded runs. Resumable native audio drains its own
history at sample boundaries and queue pressure; ordinary clocks remain eager.
Input queues are also bounded and fail
explicitly. Fault code/detail identify the first failure.

## Remaining boundaries and validation

Advancement stops at the exact asynchronous reset deadline, including inside a
multi-cycle instruction. The CPU bridge must abandon its remaining register/bus
effects and apply `device_reset` before fetching again. Reset preserves
physical time, caller EEPROM/Flash/SRAM and already-active NVM programming.

PB5/RESET has an explicit **recognized digital reset-line** profile. With
RSTDISBL unprogrammed (high-fuse bit0=1), a strong external PB5 driver going low
latches EXTRF at that injection timestamp and stops advancement there. The CPU
bridge applies `device_reset`; the CPU remains halted while the external driver
holds PB5 low. A queued high level or removal of that driver releases the line
at its timestamp. `device_reset_held()` exposes the distinction between a reset
request awaiting acknowledgment and an acknowledged reset still held active.
Register writes and CPU advancement are blocked while held; I/O/ADC clocked
state stays reset, the watchdog counter is held reset, and its oscillator time
and already-active EEPROM/Flash programming continue on the physical timeline.

Every admitted board profile requires DWEN unprogrammed. Programmed DWEN is
rejected at init with config fault1/detail14, independently of the optional
analog RESET receiver, so this digital RESET contract is never silently applied
to an active debugWIRE configuration. Its pin/startup/sleep behavior remains
unimplemented; see the [device interface inventory](../devices/attiny13a/interfaces.md).

The provided low level means an **already recognized** assertion. This profile
does not invent an analog RESET threshold, spike filter, minimum pulse width
or BOD waveform. With the default zero-startup fixture, release resumes the
digital board at the supplied timestamp. The optional fuse timing profile below
instead stretches reset after release. A fixture requiring analog recognition
must supply recognized reset transitions with those timings. Analog
voltage injections alone do not assert this digital reset line. When RSTDISBL
is programmed (high-fuse bit0=0), PB5 remains available as GPIO/ADC0 and these
digital inputs do not reset the device.

Without an explicit calibration table, runtime OSCCAL changes still fail.
The opt-in table model is described in [device-osccal.md](device-osccal.md).
BODCR's digital
sleep-disable sequencing is implemented as described below. Reads of reserved
I/O return0; nonzero reserved writes
also fault. DWDR reads0 without a debugger. A timer pulse with active phase-correct TOP=0 and
other reserved/ambiguous configurations retain the component's explicit faults.
There is no silicon/electrical trace oracle or voltage/temperature calibration.

WGM5 with OCR0A/TOP=0 is specifically **pending hardware**, not a validated
counter/IRQ model. DS40002307A section 11.7.4 describes zero-duty polarity but
does not resolve simultaneous TOP/BOTTOM counter and flag cadence;
[official errata DS80000857A](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/Errata/ATtiny13A-SilConErrataClarif-DS80000857A.pdf)
adds no Timer0 clarification. The source-only
[measurement probe](timer0-top-zero-probe.md) provides controlled external T0
stepping, raw register/physical-pin capture profiles and a trace schema without
assuming the unknown outcome. The existing explicit fault remains until that
evidence is available. It now occurs at the first unknown timer pulse, including
active TOP=0 with a nonzero pending OCR0A. A held external T0, stopped source or
clock gate does not fault just for this configuration. The board publishes the
internal pulse deadline before CPU work can cross it; no buffer transfer, flag
or OC transition is invented. Non-PWM preload remains the supported way to
establish active nonzero TOP before selecting WGM5.

`device-test.c` exports `device_test_case(index)` with16 deterministic C fixtures:
bus masks; physical PWM; synchronized T0; vector priority/ACK; ADC sample/result
locks and ADIF policy; all six auto-trigger sources; Idle; Power-down/watchdog;
CLKPR transition/protection; independent EEPROM time; Flash stall/generation;
watchdog reset preservation; bounded-buffer diagnostics; recognized RESET
assertion/hold/release at exact timestamps; NVM programming and a fuse-forced
watchdog during held reset; and RSTDISBL GPIO/ADC0 behavior. They are compiled
with all production component C files and `-Wall -Wextra -Werror`, targeting
WASM with no host imports. Tests are generated only under ignored `build/`.
All16 return0. The separate module suites continue to verify each component.

## Optional fuse startup and reset timing

Configuration key17, `DEVICE_CFG_FUSE_STARTUP_PROFILE`, accepts0/1 and defaults0.
The default preserves the existing zero-startup digital fixture. Enabling it
uses [DS40002307A section6.2, Tables6-2/6-3/6-5/6-6 and section8.2](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=30).
CKSEL selects the applicable table; it does not replace the caller's existing
`oscillatorHz` value with a nominal frequency. Source CK therefore means one
configured undivided oscillator period, independent of CKDIV8 and CLKPR.

| SUT | Power-down oscillator startup | Additional reset delay |
| --- | --- | --- |
|00|6 source CK|14 source CK|
|01|6 source CK|14 source CK +512 watchdog oscillator pulses|
|10|6 source CK|14 source CK +8192 watchdog oscillator pulses|
|11|Reserved; initialization fails with config fault/detail8|Reserved|

The internal-source tables require at least the512-pulse timeout for SUT00 when
RSTDISBL is programmed. The external-source table has no corresponding note.
The512/8192 pulses follow configured `watchdogHz`, including rational phase;
their nominal4/64ms labels are not hardcoded durations. Reset is modeled as the
asynchronous timeout followed by20 source CK. A watchdog reset first supplies
its documented one-CK reset pulse. This ordering and the retained watchdog
oscillator phase are explicit digital choices; sub-cycle silicon reset/clock
phase is not measured here. Power-on/BOD reset calls mean an already recognized
source that has become inactive; this profile does not detect analog voltages.

`device_reset` immediately resets peripheral registers and reloads OSCCAL.
The CPU and synchronous peripheral clocks remain held until the reset deadline;
CPU advancement, writes and control effects are blocked. Already-active NVM
operations and physical watchdog oscillator time continue. The watchdog counter
itself remains reset throughout this internal/external reset stretch, including
its ending edge, and starts a fresh count after release. This also permits the
long SUT10 interval with a fuse-forced watchdog. A queued external RESET release
starts the delay at its timestamp; asserting RESET again cancels/restarts it.

`device_starting()` exposes reset stretch, separately from physical
`device_reset_held()`. `device_startup_deadline()` returns its `base_half`
deadline, UINT64_MAX during external RESET hold, or current time when ready.
`device_halted()` includes both states. `device_wait_until` services their
deadlines without host callbacks. Monotonic nominal virtual time is unchanged.

Power-down wake adds only6 source CK before the existing four extra CPU cycles;
SUT's reset timeout is not charged again. Idle and ADC Noise Reduction retain
their oscillator. Fuse startup overlaps explicit caller startup and BOD recovery
by taking their maximum, preserving the previously documented overlap profile.
Ordinary interrupt entry remains CPU-owned. Missing external clock edges, clock
settling waveforms, supply ramps and oscillator calibration require a richer
physical model. `device-startup.test.mjs` covers exact boundaries, repeated and
external/watchdog resets, phase/divider independence, sleep modes, WDTON and
EEPROM/Flash completion using the actual import-free board.

## Factory oscillator calibration

Configuration key16, `DEVICE_CFG_FACTORY_OSCCAL96`, supplies the device-specific
9.6MHz calibration byte (0..127). Its default0 is an explicit digital fixture
value; it is not claimed to be the factory byte of an arbitrary chip. Every
reset loads this byte into OSCCAL, including external/watchdog resets and when
CKSEL selects4.8MHz or another source. This follows [DS40002307A section17.3](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=111):
hardware always loads the9.6MHz calibration, while using the distinct4.8MHz
calibration requires firmware action. OSCCAL bit7 is reserved, reads0 and ignores
writes. Same-CAL writes, including ones setting reserved bit7, are accepted.

Without a provided table, changing CAL[6:0] still faults with
`DEVICE_FAULT_UNIMPLEMENTED_IO`, detail0x31, preserving existing fixtures.
The optional [per-device runtime calibration model](device-osccal.md) supplies
up to128 explicit frequencies, fixed physical time and retained clock phase.
Neither a universal linear curve nor measured temperature/voltage dependence
is inferred. `device-osccal.test.mjs` covers
factory values, validation, all reset causes, fuse independence and reserved bits
using the actual import-free C/WASM board.

## BODCR sleep disable and recovery profile

The official reference is [DS40002307A sections7.2 and7.5.1](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=37).
BODCR is I/O0x30 (data0x50): BODS is bit1, BODSE bit0, reserved bits read0.
The board accepts the protected sequence: write both bits1, then within four
CPU cycles write BODS1/BODSE0. The second write authorizes SLEEP for three CPU
cycles. A lone BODS write, BODSE-only first write, late commit or expired SLEEP
does not disable BOD. CPU cycles follow the current clock divisor, whereas the
recovery interval below uses the independent physical timeline.

Control deadlines are half-open and use the existing register/control completion
edge contract: a second write at first_write_cycle+4 is late; SLEEP at
commit_cycle+3 is late. The initial BODS readback also clears after three cycles;
the initial BODSE enable expires after four. A successful commit restarts the
three-cycle BODS interval. Writes to reserved bits alone do not rearm anything.
Once accepted by Power-down SLEEP, disable is latched independently of subsequent
BODS auto-clear. It is effective only when BODLEVEL[1:0] (high-fuse bits2:1) is
not11. Idle and ADC Noise Reduction never acquire this disable state.

`device_bod_disabled()` reports this latched logical state. On an accepted
interrupt wake it clears immediately; `device_bod_recovering()` reports the
following recovery interval. Reset clears the control windows and both states.
No supply threshold, analog reset, hysteresis or voltage-induced behavior is
inferred from these booleans. Supply-voltage brown-out simulation remains a
separate analog-input feature.

Section7.2 describes recovery as approximately60us, not an exact characterized
minimum/maximum. Configuration key15, `DEVICE_CFG_BOD_RECOVERY_NS`, therefore
defaults to an explicitly approximate60000ns digital profile and accepts a
caller-supplied duration, including zero for an ideal fixture. Convert to the
unchanged half-oscillator domain with ceil(ns*2*oscillatorHz/1e9), independent of
CLKPR. The profile starts BOD recovery and caller-configured startup concurrently
and waits for max(recovery,startup); this is an explicit scheduling assumption,
not a silicon overlap measurement. Set caller startup to a measured combined
duration when available. After this hold, the existing four extra CPU wake cycles
still apply; normal interrupt entry remains owned by the CPU.

`device-bodcr.test.mjs` compiles the actual board/components with strict warnings
and checks zero WASM imports, control boundaries, invalid sequences, fuse/sleep
gating, latched state, reset, fractional-duration rounding, CKDIV8 independence
and startup overlap. Its generated test artifacts stay under ignored build/.

## Analog RESET receiver

An optional device-owned [RESET input module](../devices/attiny13a/reset_input.md)
adds voltage recognition to the same physical scheduler and reset aggregation.
`device_configure_reset_input` fields1/2 select assertion/release thresholds in
ppm of VCC; fields3/4 are qualification ns and5/6 are propagation ns. Supply all
six fields before field0 enables the profile. Physical time is required and
DWEN must be unprogrammed. RSTDISBL gates the reset role.

Queued analog PB5 values select the pad voltage; before selection it follows
VCC. RESET and VCC are passed atomically to the receiver, whose next ps deadline
participates in the device minimum and cache invalidation. Prequalified digital
PB5 reset remains an independent source. The receiver survives CPU reset and
holds the aggregate until qualified release; SUT starts after the final source
releases. With a supply observer, assertion resets peripherals before CPU
acknowledgement. Fault17 surfaces the receiver's sticky diagnostic bits.

`device_reset_input_enabled`, `device_reset_input_asserted` and
`device_reset_input_deadline_ps` expose receiver diagnostics. It does not add an
external programmer. Browser/CLI configuration and portable package v4 use the
same six-field profile; older package versions retain their earlier contracts.
