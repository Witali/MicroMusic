# Conservative same-state deadline cache

This is a design review, with no production change or new benchmark. It audits
root `device.c` at commit `bfc3d47` (including physical clocks and the POR/BOD
observer), normalized-LF SHA-256
`5b0a3fb99380bbef314fd06ed2cca2e8e3cb9058e163e56a0c364cef673ddf5c`.
The working bridge reviewed during the audit had normalized-LF SHA-256
`1aafc94069e9fc26c9a6e3a70fa7cacde9d3ec0461543019de3aaa94e983d310`;
it was not committed yet. Re-audit the mutation coverage if these sources change.
The existing sampling profile motivates reducing repeated scans; its percentages
are not measurements of this newer clock/power integration.

## Minimal implementation boundary

Keep the current scanner body once, renamed `next_event_scan()`, and memoize its
absolute result in a wrapper retaining the `next_event()` name. Do not cache a
relative CPU budget, `overflowAt`, pending IRQs or the caller's minimum with an
audio/run deadline. The cached time has the same units as `board.base`: legacy
half-oscillator units or physical picoseconds, selected at initialization.

Add only private board state:

```c
struct {
    uint64_t base, at;
    uint8_t valid;
} deadline;
```

`UINT64_MAX` remains a valid cached “no event” result; `valid` is separate.
Initialization's existing zero assignment clears it. A Boolean suffices: no
generation counter, wrap handling or duplicate peripheral-state fingerprint is
needed for this single-threaded, callback-free board.

Illustrative wrapper, with the current scanner unchanged:

```c
static inline void deadline_invalidate(enum deadline_reason reason) {
    (void)reason;                 /* no logging/counters in the hot path */
    board.deadline.valid = 0;
}
static uint64_t next_event(void) {
    if (board.deadline.valid && board.deadline.base == board.base)
        return board.deadline.at;
    board.deadline.valid = 0;
    uint64_t at = next_event_scan();
    if (!board.fault) {           /* scan arithmetic can call fail() */
        board.deadline.base = board.base;
        board.deadline.at = at;
        board.deadline.valid = 1;
    }
    return at;                   /* preserve the scanner's failure result */
}
```

Always invalidate **before every `elapse` and every `service`**, even if the
target/virtual half-cycle is unchanged. Do not retain this first cache across a
time advance. It makes no algebraic assumptions about retained clock phases,
ADC gating, timer prescaling, watchdog progress, or NVM wall-time conversion.

Keep `device_next_cpu_event()`'s initialization/fault/reset/hold/startup/recovery
guards in place. Recompute its rounded-up CPU distance from the absolute result,
current source rate, divisor and phase each time. A guard return of zero is not
an absolute event and must not enter this cache.

## Required invalidation hooks

These are the complete top-level mutation boundaries in the audited board. Put
the hook before the first mutation/helper call, not only at successful returns:

```c
enum deadline_reason {
    DEADLINE_INIT, DEADLINE_ELAPSE, DEADLINE_SERVICE,
    DEADLINE_READ, DEADLINE_WRITE, DEADLINE_IRQ_ACK,
    DEADLINE_CONTROL, DEADLINE_LPM, DEADLINE_INPUT,
    DEADLINE_RESET, DEADLINE_FAULT
};
```

| Boundary | Placement and reason |
| --- | --- |
| `device_init` | Existing `board=(device_t){0}` already invalidates; keep an explicit INIT hook after it if helpful. Covers copied configuration, calibration table, timing contract, power profile and all initial nested resets. |
| `elapse` | ELAPSE before changing **any** base/half/phase/ns/WDT phase field, including zero delta and the fault-accounting path. |
| `service` | SERVICE at entry, including zero-time re-service and early error returns. Covers every autonomous event and downstream wake/reset/domain change. |
| `device_read` | READ before dispatch. Reads can advance NVM/timer/analog or expire BOD/WDT windows; ADCL locks data. Do not classify the whole bus-read API as pure. |
| `device_write` | WRITE before dispatch, including no-op writes and SREG/SPL writes: the common `sources(); wake(); ...` tail can still mutate board state. All accepted/failed/early-return branches remain covered. |
| `device_ack_irq` | IRQ_ACK before any flag clear or watchdog-mode change and before the subsequent ADC source delivery. |
| `device_control` | CONTROL before dispatch. Covers SLEEP/domain/BODS/ADC start, WDR counter restart, SPM programming, and all SPM early returns. |
| `device_lpm` | LPM before `nvm_lpm`; special fuse/lock LPM consumes the RFLB command/window, and every LPM can advance NVM. |
| `queue_input` | INPUT before accepted insertion/count mutation. All digital/analog/VCC and legacy/ps wrappers share it. Equal-current-time injections are applied immediately without an `elapse`, so an elapse-only hook is insufficient. |
| `device_reset` | RESET before clearing `reset_requested` and **before** the `reset_preapplied` acknowledgment return. Do not hook only `reset_state()`. |
| `fail` | FAULT on every call, before/with the first-fault latch. Covers errors in scan arithmetic, getter time contracts, overflow and rejected inputs. Never publish a scan into the cache after it faults. |

For rejected input/read/write paths that only call `fail`, that hook already
covers the error. Conservative extra clearing on entry is harmless. This design
intentionally does not try to preserve a cache through a no-op bus access.

There are currently only four board scanner call sites: the loop head and
endpoint check in `advance_to`, `device_next_cpu_event`, and `wait_until`'s loop.
None runs inside `service`, bus dispatch, reset or input mutation. Nested
`analog_next_event`/`power_reset_next_deadline` calls belong to those modules and
do not query the board cache. Therefore one entry hook per transaction is enough;
there is no partial-transaction cache publication to invalidate a second time.
If a future helper begins querying the board scanner mid-transaction, add an
invalidation after subsequent mutation or explicitly suppress cache publication
while that transaction is open. Do not silently rely on today's call graph.

## Scanner dependency and mutation map

`next_event` is at lines 424–448 of the audited source. This table covers every
candidate plus the conversion/gating state it reads, including transitive
dependencies of the peripheral query functions.

| Candidate/dependency | State that changes it | Mutations covered by the hooks above |
| --- | --- | --- |
| All `at_half`/`at_cycle` conversions | `base`, `half`, fractional `phase`, actual `divisor`, `oscillator_hz`; `physical`/copied source configuration select the time denominator | ELAPSE; WRITE for OSCCAL and protected CLKPR requests; SERVICE for the deferred divisor edge and phase reset; RESET/INIT for fuse divisor, factory calibration and time-contract selection. |
| Timer0 `timer0_next_event` | Cycle, prescaler phase, running/gated state, PRR/TSM/PSR10, CS/WGM/TOP, active buffered OCR values, direction/count, comparison blocking and pending fast-clear state | WRITE for all timer/PRR registers; SERVICE for pulse/compare/TOP/BOTTOM/buffer transfer and synchronized external T0 edges; domain changes inside service/control/write; RESET/INIT. |
| GPIO next half-edge | `io_running`, digital input level, latch/PINB pipeline, PCINT mask/previous/edge state, INT0/T0 synchronizer/detector state; current `half` | WRITE for PINB toggle, DDRB/PORTB, DIDR0, PCMSK, MCUCR, GIFR/GIMSK; INPUT for external levels; SERVICE for sampling, timer pin overrides and reset/sleep changes; CONTROL/RESET/INIT. Even a stopped-clock PCINT input can cause an immediate wake/clock change. |
| ADC next half-edge | Clock gate, conversion phase and `next_half_edge`; writes, source edges and noise-cancel start can schedule/restart work | WRITE for ADC/mux/PRR/clock configuration; READ when a read advances the ADC; SERVICE for conversion/trigger/comparator events; IRQ_ACK for flag transitions followed by `sources`; INPUT for analog/reference changes; CONTROL for sleep-triggered conversion; RESET/INIT. |
| Comparator next event | Bandgap-ready, propagation and synchronization deadlines; ADC/ACME route, ACD/ACBG/sense, pin/reference voltage, clock origin/gating and sleep clamp affect those deadlines | WRITE/READ, SERVICE, INPUT (including VCC), CONTROL and RESET/INIT via `analog_*`, `pin_voltages`, `clock_domains` and `wake`. Zero-delay input effects at the current timestamp must not be skipped. |
| NVM cycle windows | EEMPE/EECR plus `eempe_until`; SPMCSR/flash-busy state plus `spm_until`/`rflb_until` | WRITE, READ, LPM (consumes the special-read command), CONTROL/SPM, SERVICE expiration/completion and RESET/INIT. |
| NVM ns completion | EEPROM/Flash busy flags, their absolute ns deadlines and their voltage-uncertainty fault bits; `ns` and `ns_remainder` convert to base time | ELAPSE, SERVICE, WRITE/programming, CONTROL/SPM, READ/LPM advancement, RESET/INIT; INPUT/VCC and `supply_guard` can freeze a pending completion permanently. Never reuse the earlier finite completion after a supply fault. |
| Watchdog timeout | WDE/WDTIE/WDP, counter/reset-request state; board reset/held/startup gates; watchdog rate, fractional `wdt_remainder`, current base time | ELAPSE and SERVICE, WRITE/WDTCR/MCUSR, CONTROL/WDR, IRQ_ACK (combined mode can clear WDTIE), RESET/INIT, INPUT/PB5/VCC and all power aggregation reached from those transactions. |
| Watchdog write window | WDCE and absolute CPU-cycle `unlock_until` | WRITE, READ (`system_watchdog_read` expires WDCE), SERVICE, RESET/INIT; all conversions also depend on clock state above. |
| BODCR windows | `bod_arm_until`, `bod_sleep_until`, armed/committed bits; CPU-cycle conversion | WRITE/BODCR, READ/BODCR's `bod_expire`, SERVICE expiration, CONTROL/SLEEP and RESET/INIT. |
| CLKPR unlock/transition | CLKPCE + `clkpr_until`; `pending_divisor` + `clkpr_switch_half` | WRITE for both sequence stages, SERVICE for window expiry and actual divisor/phase transition, RESET/INIT. A pending write changes the future candidate before the divisor changes. |
| Sleep wake/startup | Sleep phase, `startup_until` and `ready_at` in base units; pending peripheral source masks can begin a wake | CONTROL/SLEEP; SERVICE and INPUT wake delivery; WRITE's common wake tail; RESET/INIT. PRR/domain changes can move peripheral deadlines even when this sleep candidate is infinite. |
| Reset startup | `base < reset_until`, `reset_held` and startup timeout; selected fuse profile, current source duration and watchdog timeout phase construct it | SERVICE, INPUT (assert/release), CONTROL/power wake, RESET/INIT and internal `power_sync`/`reset_startup` nested beneath those boundaries. |
| POR/BOD observer | `power_enabled`; `power.bod_deadline`, `release_deadline`, `recovery_deadline`; VCC, hysteresis/source qualification, BODS state and aggregate reset sources create/cancel them | INPUT/VCC/PB5; SERVICE qualification/release/recovery; CONTROL/SLEEP/wake; RESET/INIT. `power_sync` can reset peripherals immediately at ASSERT and set `reset_preapplied`, before the CPU acknowledgment. |
| Qualified WDT reset pulse | Nonzero `wdt_reset_end`, `raw_other_reset`, power-source aggregation | SERVICE creates and ends the pulse, INPUT can add/release an external reset while it is active, CONTROL/wake and RESET/INIT can change downstream gates. It is an explicit scanner candidate, not just the next WDT timeout. |
| Earliest queued input | `input_count`, `input_head` and `inputs[head].at`; digital/analog/VCC share the ordered queue | INPUT insertion, including accepted tail appends and current-time consumption; SERVICE consumption. Always dirty an insertion initially, even if it does not replace the head. |
| Fault/initialization/hold guards | Board fault, initialized, reset request/hold/startup, `power.recovery_deadline` | FAULT plus INIT/RESET/SERVICE/INPUT/CONTROL. Keep the public zero-distance guards outside memoization. |

`bod_recovery_until` is an observer/gating field, not an independent explicit
candidate in today's scanner: physical power recovery is represented by the
power observer deadline, and wake startup uses the sleep deadlines. Do not add or
remove scanner candidates as part of the cache patch.

Transitive helper coverage is explicit: `bod_expire` runs under READ/WRITE,
CONTROL or SERVICE; `bod_write` under WRITE; `reset_state`/`reset_startup` under
INIT/RESET, SERVICE or INPUT; `power_sync`/`power_other_sources` under INIT/RESET,
SERVICE, INPUT or CONTROL; `supply_guard` under INIT/SERVICE/INPUT/WRITE/CONTROL;
`clock_domains`, `wake`, `timer_outputs`, `pin_voltages`, `capture_pins` and
`sources` run inside those same transactions. Every helper arithmetic failure
also reaches FAULT. No direct mutator path is left dependent only on a later
`full_deadline` call.

## Operations that can retain the same-state cache

- Successful `device_pending_irqs`, `device_next_irq`, halted/sleep/reset/power
  observers and raw time/divisor/rate/flash-generation getters do not mutate a
  deadline input. SREG.I governs CPU interrupt acceptance separately.
- Pin state/event getters and `device_consume_pin_events`/`device_clear_pin_events`
  only inspect or consume already-produced output history. Ring head/count and
  dropped-history count are not scanner dependencies. A bad time-contract getter
  still reaches FAULT. Pin production overflow is covered by its surrounding
  transaction and FAULT; consuming output must not move hardware time or levels.
- `device_take_dirty_pages` clears only the translated-code dirty-page bitmap;
  it does not change NVM busy/deadline/generation state.
- `device_cpu_half_deadline_ps`, `device_cpu_halves_until_ps` and
  `device_next_sample_ps` use local conversion remainders; they do not alter the
  board's retained phase. Their errors reach FAULT. Audio sample deadlines remain
  the caller's bound and are not inserted into this board cache.
- The bridge's f64 `full_time_origin` rebasing and diagnostic `st.cyc` updates
  do not change the board's absolute time contract. Keep conversion/publication
  of `overflowAt` outside this cache; a cached absolute board timestamp must not
  be replaced by a host-call-relative f64 value.
- Pre-init `device_configure*` and `device_clear_osccal_hz` write staging globals,
  not the live board's copied configuration. The contract is configure before
  init; INIT clears the cache before adopting them. This is not permission for a
  new live-configuration API without invalidation.
- CPU register/SREG/SPL/stack memory stores do not directly feed this scanner.
  Device-owned I/O must continue through the bus; direct host mutation of
  mirrored peripheral bytes is not a supported substitute for `device_write`.

## Exact call order and expected reuse

Preserve the current `advance_to` order:

1. Query `next_event()` and take the caller's minimum.
2. `elapse(next)` invalidates before updating time/phase.
3. `service(before)` invalidates before all hardware events; preserve its current
   power/NVM/watchdog/clock/input/wake ordering.
4. If reset is requested, abort as today; do not scan or consume the remainder of
   the interrupted instruction to make a cache entry.
5. At the target, query `next_event()` after all service mutations. If its result
   is **strictly greater** than the target, return with that cache valid.
6. `full_clock` immediately calls `full_deadline`/`device_next_cpu_event`; it reuses
   that same-state absolute scan. Audio collection may then consume pin history
   without invalidating it. IRQ-entry clocks or ACK subsequently invalidate it.

If the endpoint query returns exactly the current target, keep looping and
service that timestamp as today. Never change `>` to `>=`, suppress zero-time
service, or overwrite a due timestamp with a “future” cache entry. The next loop's
ELAPSE/SERVICE hooks clear it even for a zero delta. This also preserves the
stagnation diagnostic.

`wait_until` can reuse its initial query at `advance_to`'s loop head, and a final
endpoint query at the following wait/CPU query, without extending cache lifetime
across an elapse. A second query with no mutation can also reuse a cached infinity.
This first step does not remove the full scan after each service; further
cross-time caching would need a stronger per-source invariance proof and is out
of scope.

## A small independent same-time candidate

One narrowly provable follow-up is in `analog_advance`, rather than changing
`device.c`'s service order. Keep its backward-time check first, then consider:

```c
if (time == a->adc.half_cycle &&
    time == a->comparator.half_cycle &&
    analog_next_event(a) > time)
    return 1;
```

With those conditions the original while-loop has no due work, ADC advancement
would add a zero stopped-clock interval and set the same time, and comparator
advancement would set the same time. No trigger, comparison or conversion edge
is removed. A zero-delay comparator mutation can schedule an event at this very
timestamp; the strict next-event guard then fails and the original code runs.

Do not implement a simple “last time equals current time” shortcut, remove
`sources()` after the timer/GPIO events, or skip `connect_sources()` just because
external source bits look unchanged: comparator flags and auto-trigger edge
history can change at the same timestamp. The candidate saves only duplicate
time advancement; source delivery still runs in its current order. Its benefit
needs measurement after integration; none is claimed here.

## Meaningful validation before enabling either change

Reuse the actual production scanner as the oracle, not a second hand-maintained
scheduler or copied board-state mirror. A C fixture can include `device.c` once
and expose its private cached wrapper and single `next_event_scan` for assertions
on the **same real board** after each public operation. Separately, an uncached
build can bypass only the memoization wrapper while retaining that same scanner
body and all production service/bus code. No alternate device model is needed.

Required targeted cases must prime the cache **before** each mutation, perform
the mutation at the same timestamp where possible, then compare cached and raw
deadlines plus physical trace/state:

1. Timer start/stop, prescaler reset/hold, TCNT compare blocking, TOP/buffer
   transfer, FOC, PRR and external T0; include a newly earlier deadline and
   cancellation to infinity.
2. GPIO stable-to-unsettled injection, DDR/PORT/PIN toggle, DIDR/PCMSK/INT0 sense,
   stopped-clock PCINT and same-time events after sampling. Enqueue head/current
   input and append a later tail through all digital/analog/VCC APIs.
3. ADC conversion start/auto source switch/flag ACK and ADCL locking; comparator
   zero propagation, bandgap startup, mux/ADEN/ACME changes and clock gates.
4. Both protected CLKPR stages and the actual deferred edge; accepted OSCCAL
   changes with a nonzero retained phase in the fixed-ps contract, external-clock
   calibration writes, reset loading the factory byte, and large timestamps.
5. Watchdog WDR, WDCE read/window expiry, WDP/mode changes and combined-mode ACK;
   reset exactly inside a multi-cycle instruction and a power-profile WDT pulse.
6. NVM EEMPE/SPM/RFLB windows, special LPM consumption, EEPROM/Flash completion,
   programming surviving reset, and VCC uncertainty freezing the former finite
   completion. Compare Flash generation and dirty pages as well as bytes.
7. BODCR arm/commit expiry; SLEEP/wake/startup; PB5 held/released; qualified POR/BOD
   assertion, additional HOLD causes, release, recovery and `reset_preapplied`
   CPU acknowledgment. Check that reset deadlines abort later bus effects.
8. Repeated pure queries, pin-ring draining, dirty-page draining and caller/audio
   bounds; zero-time due events, cached infinity, timestamp reversal, arithmetic
   overflow and ring/queue overflow. A scan that faults must never leave a valid
   cached answer; preserve the first fault/detail and the existing stop policy.

Compare end-to-end cached/uncached firmware execution for raw PCM bytes, pin event
timestamps/levels/drive state, base time, virtual halves, clock phase/divisor/rate,
visible registers/I/O/SRAM, IRQ entry/ACK counts and reset/sleep/NVM state. Vary the
number of extra read-only deadline queries and advancement chunk sizes. Existing
`device-scheduler`, `device-clock`, `device-osccal`, `device-bodcr`,
`device-startup`, `device-power`, `nvm-voltage`, peripheral tests, and translated
physical-clock/power tests supply real behavioral fixtures to extend.

For the analog shortcut, add explicit current-time propagation/ADC-trigger tests,
stopped-clock zero deltas, new same-time input/reference mutations and a pending
deadline exactly equal to the current timestamp. A public API idempotence test
alone cannot catch a shortcut that incorrectly drops newly scheduled zero-delay
work.

After those checks pass and root's active full suite finishes, measure the same
captured intervals with the single cache wrapper enabled/bypassed and profile
again. This design review deliberately ran no tests or benchmarks alongside that
suite and predicts no speedup.
