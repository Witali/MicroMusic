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
`device_next_cpu_event` returns a rounded-up CPU-cycle **distance**, not an
absolute timestamp; a whole instruction that crosses an event still advances
through that event internally.

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
Same-time mutations coalesce. `device_pin_events` exposes a contiguous ring
batch and `device_consume_pin_events` releases it without allocation or copying.
A C renderer can integrate intervals into audio and call JavaScript once per
audio block. No output transition invokes JavaScript.

Buffer overflow latches `DEVICE_FAULT_OUTPUT_OVERFLOW` and increments a visible
drop counter; callers must drain the ring during bounded runs. Input queues are
also bounded and fail explicitly. Fault code/detail identify the first failure.

## Remaining boundaries and validation

Advancement stops at the exact asynchronous reset deadline, including inside a
multi-cycle instruction. The CPU bridge must abandon its remaining register/bus
effects and apply `device_reset` before fetching again. Reset preserves
physical time, caller EEPROM/Flash/SRAM and already-active NVM programming.

BODCR brownout-disable sequencing and runtime OSCCAL frequency recalibration do
not have calibrated physical models in these modules. Writes requesting those
behaviors fail explicitly. Reads of reserved I/O return0; nonzero reserved writes
also fault. DWDR reads0 without a debugger. Sustained phase-correct TOP=0 and
other reserved/ambiguous configurations retain the component's explicit faults.
There is no silicon/electrical trace oracle or voltage/temperature calibration.

`device-test.c` exports `device_test_case(index)` with13 deterministic C fixtures:
bus masks; physical PWM; synchronized T0; vector priority/ACK; ADC sample/result
locks and ADIF policy; all six auto-trigger sources; Idle; Power-down/watchdog;
CLKPR transition/protection; independent EEPROM time; Flash stall/generation;
watchdog reset preservation; and bounded-buffer diagnostics. They are compiled
with all production component C files and `-Wall -Wextra -Werror`, targeting
WASM with no host imports. Tests are generated only under ignored `build/`.
All13 return0. The separate module suites continue to verify each component.
