# ATtiny13A power-reset observer

`power_reset.c/.h` is a standalone deterministic observer of piecewise-constant
VCC inputs. It models reset assertion, source hold and release deadlines in C,
without host imports, callbacks or CPU-clock polling. The board remains
responsible for resetting registers/CPU, latching MCUSR, startup clocks, NVM and
pin state. These files do not claim complete analog or silicon behavior.

The observer must survive ordinary CPU/device resets: retain its VCC, active
source levels and deadlines until the supply/reset source actually changes.
Re-initializing it from the CPU reset handler would lose a brown-out hold.

## Official basis and electrical ranges

Primary source: [Microchip ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
Page references below are the PDF's printed page numbers, not stale page
references retained inside the document's older contents/cross-references.

| Subject | Source |
|---|---|
| Asynchronous reset of I/O; delay after all reset sources release | §8.1, Figure8-1, p41 |
| POR and post-rise timeout | §8.2.1, Figures8-2/8-3, p42 |
| BOD hysteresis, pulse qualification, timeout | §8.2.3, Figure8-5, p43 |
| Software BOD disable and recovery | §7.2 p37; BODCR sequence §7.5.1 p39 |
| MCUSR flag persistence/clear rules | §8.5.1, p48 |
| BODLEVEL fuse bit positions and latching | §17.2, Table17-3, pp110–111 |
| Electrical thresholds | §18.5, Tables18-4/18-5/18-6, p126 |

The generic `VPOT` in §8.2.1 is refined by the enhanced POR table into separate
activation (`VPOA`) and release (`VPOR`) thresholds:

| Parameter | Min | Typ | Max | Qualification |
|---|---:|---:|---:|---|
| VPOA | 0.6V | 1.3V | 1.6V | Guidelines only |
| VPOR | 1.1V | 1.4V | 1.6V | Guidelines only |
| BODLEVEL10 VBOT | 1.7V | 1.8V | 2.0V | Table18-6 note applies |
| BODLEVEL01 VBOT | 2.5V | 2.7V | 2.9V | Table18-6 note applies |
| BODLEVEL00 VBOT | 4.1V | 4.3V | 4.5V | Table18-6 note applies |
| BODLEVEL11 | — | disabled | — | Default unprogrammed fuses |
| VHYST | — | 50mV | — | Not production tested |
| tBOD | — | 2µs | — | Not production tested |

Both 50mV and 2µs are in the **Typ** column; the pulse-width parameter's name
does not turn the typical number into a guaranteed exact filter duration.
The enhanced POR table additionally gives a minimum power-on slope of
0.01V/ms and says POR requires an earlier VCC level below VPOA. Min/typ/max
values should not be combined into a physically impossible chip: select a
consistent profile, including `por_release_uv >= por_assert_uv`. The API accepts
custom measured/profile thresholds instead of pretending each chip switches at
the typical values. Continuous ramp slopes, temperature, metastability and
operation outside the electrical ratings are not inferred from this step-input
model.

## Contract

All voltages are nonnegative integer microvolts. All timestamps and durations
are `uint64_t` in one caller-selected physical time unit, independent of CPU
frequency or CLKPR. `UINT64_MAX` means no deadline and is never a valid input
timestamp. WASM exposes i64 as signed JS BigInt; an FFI inspecting the sentinel
must use `BigInt.asUintN(64, value)`.

`power_reset_typical_profile(profile, filter_ticks, timeout_ticks,
recovery_ticks)` fills typical voltage values only. Each timing argument is
mandatory and can be replaced by measured/selected data. Example physical 1ps
profile: `filter_ticks=2000000`, `recovery_ticks=60000000`; these explicitly
choose typical 2µs and approximately 60µs behavior. `timeout_ticks` is the
post-source tTOUT. The existing device clock owner computes fuse startup
14CK/SUT; pass **0** here when that owner already charges the reset/startup
delay. Do not add the same tTOUT twice.

`power_reset_init` copies the profile and latches `(fuse_high>>1)&3`. To
represent a cold power-on, initialize at VCC0, then inject a ramp represented
by timestamped steps. Initializing directly at a high VCC represents an
already-powered observer and does not invent a previous POR event.

`power_reset_set_vcc(state, at, microvolts)` advances internal deadlines up to
`at`, then applies that VCC step. Inputs must arrive in time order. Future
input queues belong to the board; this function applies the supplied timestamp
instead of scheduling it for a later call. `power_reset_advance` processes only
deadlines. `power_reset_next_deadline` permits direct jumps across stable spans
in O(number of transitions), including when no CPU or oscillator clock runs.

The 32-entry event ring emits ASSERT, HOLD and RELEASE. Each entry includes
timestamp, next deadline, currently active source mask, accumulated causes and
MCUSR `flags_clear`/`flags_set`. Apply clear first, then set. POR clears bits1–3
and sets PORF; a newly asserted BOD adds BORF. HOLD can report a new cause
during an existing reset, a source dropping, or the start of tTOUT. RELEASE
contains the reset episode's causes before their history is cleared. Physical
reset stays asserted until every source is inactive and the timeout expires;
another source assertion cancels/restarts that timeout. A changed cause while
already held is not a second CPU restart. The board must drain the ring before
it fills; overflow is a sticky explicit fault, never silently discarded success.

`power_reset_set_other_sources` optionally aggregates already-qualified EXTRF
and WDRF level masks. Their owners supply pulse start/end; this module does not
invent a WDT pulse width or external RESET pin analog qualification. Aggregate
sources allow one delay counter to begin only after all raw sources release.

`power_reset_set_inputs(power, at, vcc_uv, other_sources)` applies a supply and
already-qualified EXTRF/WDRF update atomically. Both values are validated before
time advances or either input changes. Valid calls first process existing due
deadlines, update both inputs, evaluate their aggregate once, then process any
new zero-duration deadlines. Use this API when a voltage-sensitive RESET
receiver changes alongside VCC: POR-to-EXTRF and EXTRF-to-POR handoffs remain
held, including with zero timeout, without a fictitious release and second
assertion. The two individual setters are wrappers preserving the other input.
This does not merge independent, sequential input calls or erase events from
deadlines already due at the input timestamp.

`power_reset_sleep` accepts MCUCR.SM0/1/2 and an already-authorized BODS state.
Only Power-down disables a fuse-enabled BOD. BODCR's timed write sequence and
CPU-cycle windows stay with the register owner. `power_reset_wake` re-enables
BOD immediately and emits RECOVER; execution stays gated until its selected
recovery deadline emits READY. Those events do not set MCUSR or assert physical
reset. A real reset cancels the sleep-only disable and recovery wait.
`power_reset_execution_blocked` combines reset hold, wake recovery and faults;
`power_reset_bod_enabled` reports whether the BOD monitor is enabled.

## Explicit digital conventions and uncertainties

- POR activates strictly below its activation threshold and releases its source
  at/above its release threshold. BOD qualifies strictly below VBOT−; a
  qualified BOD stays active until strictly above VBOT+. For odd integer
  hysteresis, lower half rounds down and upper half rounds up. Exact analog
  equality is not a silicon guarantee.
- The selectable filter requires a continuous below-VBOT− interval. Entering
  the hysteresis band before qualification cancels it; after qualification the
  hysteresis hold applies. The datasheet does not specify the prequalification
  filter circuit's internal response inside that band.
- A filter interval qualifies at its configured deadline, processed before an
  input at exactly that timestamp. Shorter pulses are ignored by this chosen
  profile; real shorter-than-typical pulses are not guaranteed to be ignored.
- While POR is active, BOD qualification is suppressed rather than treating a
  comparator at zero supply as a functioning analog circuit. After POR releases,
  BOD qualification resumes and can add BORF during the reset delay. The exact
  power-up interaction of internal analog circuits/flags is not specified.
- During BOD wake recovery, the digital voltage observer starts its filter
  immediately while CPU execution remains gated. A qualified low supply can
  therefore reset the device before recovery ends. The precise transient
  comparator behavior during startup is not an analog claim.
- Reset assertion is asynchronous to CPU retirement. The board must apply the
  event timestamp and abort later effects of an interrupted instruction, rather
  than checking reset only at the next instruction boundary.
- `init` and timing APIs report failure explicitly. Bad inputs, backward time,
  arithmetic overflow and event overflow latch a fault and block execution.
  Re-initialization clears that fault. A sleep request while already blocked is
  rejected without adding a fault.

## Supply drops during NVM operations

[Microchip DS80000857A](https://www.microchip.com/DS80000857), §2.2.1 p3,
applies the EEPROM-below-1.9V write-failure erratum to revisions G, H and I.
The outcome is **might fail**, not a specified erased value or bit pattern.
The BOD1.8V setting, particularly with its documented range, does not establish
that every EEPROM write remains above 1.9V.

`power_reset_eeprom_voltage_uncertain` exposes `VCC<1900000µV` for the NVM
owner to record an explicit out-of-profile/uncertain outcome. It does not
destroy bytes, guarantee successful writes at the threshold, or fabricate a
random failure distribution. For an in-flight write, track the condition over
the whole operation rather than checking only its final timestamp.

DS40002307A §5.3.6 p25 and §16.7 p107 explain that an already-started EEPROM
or Flash write can complete through reset **when supply remains sufficient**.
CPU reset alone therefore must not universally cancel an NVM operation. A
supply failure also invalidates unconditional successful completion: Flash
corruption, incorrect execution, charge-pump failure and partial-cell states
are analog/out-of-spec outcomes without a defined deterministic data pattern.
This observer does not own NVM contents and does not claim to simulate those
outcomes. The Flash temporary page buffer has a separate documented reset
rule (§16.2 p104) that the NVM owner must keep.

## Verification

`node --test web-player/tests/power-reset.test.mjs` compiles only this C module
and an ignored generated fixture using the read-only Emscripten SDK, with
`-Wall -Wextra -Werror`; resulting WASM has no imports. Tests cover every fuse
code, POR/BOD/filter boundaries, hysteresis, timeout restart/aggregation,
BODS/recovery, MCUSR event metadata, partition-independent advancement,
explicit custom profiles, voltage uncertainty and overflow/time errors.
