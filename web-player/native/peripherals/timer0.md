# ATtiny13A Timer/Counter0 module

`timer0.c` and `timer0.h` are a standalone C11 peripheral with an allocation-free
ABI. The production player is not modified by this module. It is intended to
link into the existing C/WASM CPU and run in the same linear memory.

The device source is Microchip's [ATtiny13A data sheet DS40002307A](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 7.3/7.5.3 and chapters 11–12 (PDF pages 37–40 and 65–84).
[AVR Instruction Set Manual DS40002198A](https://ww1.microchip.com/downloads/en/devicedoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
defines instruction timing; the CPU owner supplies those cycles to this module.

## Implemented device behavior

| WGM | Counting | TOP | OCR update | TOV |
|---|---|---|---|---|
| 0 | Normal | 255 | Immediate | MAX to zero |
| 1 | Phase correct PWM | 255 | TOP | BOTTOM |
| 2 | CTC | OCR0A | Immediate | MAX to zero |
| 3 | Fast PWM | 255 | TOP | TOP |
| 5 | Phase correct PWM | OCR0A | TOP | BOTTOM |
| 7 | Fast PWM | OCR0A | TOP | TOP |

Table 11-8 specifies TOP buffering for this chip's fast PWM. Both channels have
COM actions, inversion, PWM extremes, and non-PWM FOC strobes. TCNT writes block
one timer pulse's comparisons. OCF acts one timer clock after equality; TOV acts
at its counting boundary. GTCCR implements PSR10 and TSM. Prescaler phase keeps
running when CS selects stop or external T0; PRTIM0 and clkI/O gating freeze it.
PRTIM0 also prevents Timer0 register access. Reserved WGM/COM settings fail
explicitly. OCR0A is I/O **0x36**, OCR0B is **0x29**; 0x2a is not a Timer0 register.

The earlier player mapping of reserved 0x2a to OCR0A has been removed. Retained
stereo firmware writes the actual OCR0A address in both reset and interrupt code.

## Time and CPU integration

Timestamps are unsigned 64-bit counts of clkI/O cycles. Initialize with the
current CPU epoch and call `timer0_advance(&timer, target_cycle)` to synchronize.
The call visits compare/TOP/BOTTOM boundaries and jumps over linear counter
ramps, without iterating all CPU clocks or making any host calls. For example,
1,048,576 normal-mode clocks with OCR values 100 and 200 require 12,288 event
boundaries. A `scheduled_events` counter exposes this diagnostic.

`timer0_next_event` returns the earliest autonomous boundary, or `UINT64_MAX`.
The CPU can stop generated blocks there, advance peripherals, arbitrate IRQs,
and continue. There can already be an IRQ pending before that deadline:
`timer0_irq_pending` returns `TIFR0 & TIMSK0`, independent of SREG.I. The CPU owns
global masking, interrupt priority/vector dispatch, entry timing and SEI/RETI
latency. On accepting a vector, pass its flag to `timer0_irq_ack`. W1C uses
`timer0_write(..., TIMER0_TIFR0, bits)`.

Read/write functions first advance through the requested cycle, then apply
the access. An access therefore occurs after that boundary's timer pulse.
For TCNT writes the written value has priority over the count. Writes block
comparison on the next timer pulse, including a pulse after a stopped timer
restarts. The CPU must place accesses at the actual instruction bus cycle and
order simultaneous GPIO/peripheral changes consistently; merely synchronizing
once at the end of a multi-cycle instruction is insufficient for precise I/O.

`timer0_set_clock_enabled` gates clkI/O. Idle leaves it enabled; ADC Noise
Reduction and Power-down disable it. Runtime CLKPR changes remain the system
clock owner's responsibility: the API counts clkI/O edges, not wall-clock time.

`timer0_external_edge(&timer, cycle, rising)` counts immediately at that cycle
when CS selects that polarity. Its input must already have passed the GPIO T0
synchronizer and edge detector. The system/GPIO module supplies the phase
dependent raw-pin delay; no fixed asynchronous delay is guessed here.

## Output capture without JavaScript callbacks

The caller supplies a `timer0_event_t[]` buffer to `timer0_init`. Each 16-byte
record contains a uint64 cycle and two byte masks: OC latch levels and output
mux overrides, with OC0A/PB0 in bit 0 and OC0B/PB1 in bit 1. DDRB, GPIO drive,
pullups, input sampling and pin conflicts belong to the GPIO owner. Compare
latches keep their values while disconnected. Mux changes are captured too.

Changes at a common cycle coalesce into one final snapshot. A C audio renderer
can integrate constant pin levels over the intervals between snapshots, filter
them, and return one audio block to JavaScript. `timer0_events` exposes a
contiguous ring batch; `timer0_consume_events` releases it. Neither function
copies events or calls the host.

The buffer never grows. A full buffer drops new records, preserves exact timer
state, and increments `dropped_events`. A nonzero value is an explicit capture
failure, not permission to produce plausible audio with missing transitions.
Size/drain the ring in the C renderer before reaching that condition. `NULL,0`
explicitly disables capture for CPU/peripheral-only tests.

## Validation and boundaries

Run from the task/repository root:

```text
node --test web-player/tests/timer0-peripheral.test.mjs
```

The test compiles a temporary WASM binary under ignored `build/tests/timer0/`;
set `EMSDK` if the repository's existing local SDK cannot be found. It uses the
SDK read-only. All 12 groups compile with `-Wall -Wextra -Werror`, verify zero
WASM imports, check manually specified waveforms/flags, and compare event jumps
with individual CPU-clock stepping through 9,000 deterministic random scenarios.
Cases cover all divisors and supported WGMs, delayed OCF, missed lowered CTC TOP,
force compare, buffer timing, phase-correct MAX-to-duty transitions, clock gates,
external edges, capture overflow, and timestamps beyond 2^32.

There is no silicon trace oracle yet. These tests establish the documented
digital model and event-jump equivalence; they do not establish electrical or
oscillator fidelity. Raw external-pin phase belongs to the GPIO module.
Sustained WGM5/TOP=0 has no fully specified counter/IRQ cadence in the checked
device sources, so `TIMER0_ZERO_PHASE_TOP` rejects it instead of inventing one.
This corner is pending hardware; the [source-only probe](timer0-top-zero-probe.md)
records observations without supplying a predicted waveform. An initial
zero active TOP may load a nonzero buffered OCR0A on its first pulse. Reserved
WGM4/WGM6 and PWM COM0B=1 also return explicit errors. Fast-PWM TOP=0 is supported.

The data sheet's fast-PWM COM summary tables say “TOP” for output restoration,
while section 11.7.3 explicitly describes restoration on TOP-to-BOTTOM. This
module follows the prose for output restoration and table 11-8 for OCR latching.
Hardware traces should verify transitions where the buffered TOP itself changes.
