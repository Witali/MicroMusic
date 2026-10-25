# Settled GPIO activity and ownership audit

Baseline: `61bafe9f`, native SHA
`33cbb4e4b7b6727f510793e1149099a48c77692bc013755ae739edc4b650c02a`.
The low-level GPIO module already skips a stable span in O(1); the remaining
cost is recurring board dispatch and repeated full settled-predicate queries.
External observation/connection masks do not determine whether GPIO is needed.

## Device roles and dependencies

Microchip DS40002307A Table10-3 defines CLKI on PB3, T0 on PB2, INT0 on PB1,
OC0A/B on PB0/PB1 and PCINT0–5. There is no CLKOUT pin role or CKOUT fuse in
this device's complete pin/fuse tables. The previous plan's CLKOUT wording was
corrected at `61bafe9f`; it was never an implemented hardware feature.
Use the pinned Microchip ATDF/register views, not another AVR's pin map.

The settled predicate covers digital/latch/PINB equality, the PCINT mask/history
and delayed edge, INT0 history, and all T0 synchronizer/detector stages. A stable
physical pin alone is insufficient. Keep flag generation even when IRQ delivery
is masked, input readback for unconnected pins, asynchronous wake detection,
Timer0 alternate outputs and clock phase. Low-level INT0 remains a live condition.

## Selected board-owned certificate

The retained change adds one private board byte: true certifies the complete original
GPIO predicate. False means unknown; it is never used to suppress service.
The public system_gpio_t layout/functions and their const predicate are unchanged.
Direct low-level C users retain the original uncached behavior.

For internal clocks, a certified pipeline can skip system_gpio_advance and the
GPIO deadline query. The original deadline is infinite in this state. Retain
the final clock_high update only when clkI/O runs and the virtual half changes;
zero-length/gated spans preserve it. Reverse time falls through the original
validation and produces the same first fault. No other controller or register
publication is skipped. Existing board event-cache invalidation stays unchanged.

The first variant recomputed the predicate after each uncached advance. Its
long HQ4 row was 0.930x, with substantial control variation. The revised variant
reuses the already-computed GPIO deadline result instead: certify only a raw
UINT64_MAX answer with internal clocks, clkI/O running and half!=UINT64_MAX.
The latter guards matter because a gated clock or exhausted timestamp can also
return UINT64_MAX without a settled pipeline. Certification adds no extra full
predicate query. Keep the two variants' sources and measurements separate.

CLKI bypasses this certificate entirely: every delivered source/main-clock phase
uses the original GPIO path. PB3 remains shared by source input, GPIO, ADC3 and
pin capture. The certificate is not a license to skip physical source edges.

| Board mutation owner | Invalidation |
| --- | --- |
| reset_state / system_gpio_reset | Clear before resetting GPIO, including power-preapplied reset. |
| clock_domains / system_gpio_sleep | Clear before changing clkI/O or Power-down input clamping. |
| timer_outputs / system_gpio_timer_outputs | Clear when Timer0 override mask/levels change. |
| device_write / accepted system_gpio_write_masked | Clear for the complete GPIO register group, including PINB toggles, PCMSK/DIDR0, MCUCR and flag/control writes. |
| gpio_external / internal-source input delivery | Clear before applying resolved external inputs. The CLKI branch keeps its original policy. |

IRQ acknowledgement changes GIFR only, which is not a settled-predicate input;
it need not clear the certificate. CLKPR/OSCCAL writes do not themselves change
the pipeline values; timing conversion and any subsequent unsettled edges retain
their original paths. clock_high's CLKI initialization is outside the predicate.
The low-level floating-input mutator is not exposed through this board; adding
it or any other dependency writer requires an invalidation hook. Never derive
validity merely from unchanged PORTB or an empty host observer list.

## Validation boundary

DEVICE_GPIO_IDLE_CACHE=0 explicitly selects original board dispatch for the
focused C oracle. Both policies use the real GPIO/peripheral implementations.
Eighteen board cases compare every controller, phase, timestamp, queue and memory;
only the new certificate byte is excluded from canonical snapshots. Each true
certificate is independently checked against the full original predicate.
Tests cover compatible/physical/CLKI sources, seeded mutations, Timer0/T0,
sleep/PRR/IRQ, RESET/POR, zero/reversed spans, clock changes and PINB latency
before/at/after a falling edge. Gated/unsettled inputs and the raw time-limit
sentinel separately exercise the guards on an infinite query result. The
17 unchanged low-level GPIO cases also pass.
The generated-CPU 15-case parity matrix passes with the original ABI/CPU bytes.

Source-entry counters prove stable internal service/query dispatch disappears;
CLKI counts remain equal. Exact native rebuild/link maps show the certificate
uses existing padding after VCC: board stays 45,800 bytes at the same address.
The revised candidate is 118,946 bytes (+204), with the original 109 function exports,
fixed two pages/8192-byte stack and no host imports. These are correctness and
work-removal observations. The separate six-row balanced timing matrix measures
0.992–1.069x medians, with substantial identical-runtime control variation.
The shortcut is retained for removing proven redundant work, not as a proven
elapsed-time gain. All 1,722 default/shared-tool tests pass. The first variant
is superseded; do not pool its timings with the revised runtime. See the
[measurements and isolated replay](../reports/gpio-idle-20261025.md).

References: [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections9.2,10.2–10.4,12.3 and17.2;
[official DFP 3.4.278](../vendor/microchip/ATtiny_DFP/3.4.278/README.md);
[GPIO module contract](peripherals/system_gpio.README.txt).
This is the documented digital model, not measured metastability/electrical timing.
