# Runtime OSCCAL and physical time

Official reference: [Microchip ATtiny13A DS40002307A](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/DataSheets/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections6.2,6.3,6.4.1,17.3 and18.4.1. Section6.4.1 specifies CAL[6:0], its
reserved bit7, frequency trimming and calibration safety limits. Its typical
range table and plots do not supply a universal CAL-to-frequency curve. The
values below are caller-provided per-chip measurements or explicit fixtures.

## Configuration and errors

Before `device_init`, call `device_configure_osccal_hz(cal,hz)` for any of the128
CAL entries. CAL accepts0..127, Hz accepts0..1,000,000,000; zero is unknown.
Calling the function explicitly selects physical time even if that entry is
zero. `device_clear_osccal_hz()` removes the table and restores the original
fixed-frequency contract for the next init. Configuration is copied at init;
later changes never mutate a running instance. Missing entries are not
interpolated, extrapolated, aliased or synthesized from neighboring values.

The factory OSCCAL96 entry must exist. With CKSEL01/10 it must equal configured
`oscillatorHz`, so initialization cannot silently override two conflicting
inputs. Missing factory entry, conflicting initial frequency and an incomplete
NVM profile produce config fault1 with detail9,10 and11 respectively. Writing
a missing CAL produces `DEVICE_FAULT_OSCCAL`14/detailCAL and preserves the old
register/frequency. Without any table, CAL changes retain legacy fault12/io0x31.

Every reset reloads factory OSCCAL96 and its frequency, preserving physical time
while resetting the prescaler phase as before. Both4.8/9.6MHz selections use the
table for the selected RC oscillator's actual frequency; the caller supplies
the appropriate measurements for that selection. Section17.3 still requires
the9.6MHz factory **byte** on reset even when4.8MHz is selected. CKSEL00 external
and CKSEL11 independent128kHz sources keep their configured main frequency when
OSCCAL changes. Their CAL still requires an explicit RC table entry; this does
not convert either source into a calibrated RC source.

The digital transition is explicit: a write changes the rate immediately at its
bus-effect timestamp, preserving fractional oscillator/divider phase and all
nominal CPU-half-clock state. The remaining fraction of the current period runs
at the new rate. CLKPR, Timer0 prescaler/count, GPIO synchronizer stages, ADC
prescaler/conversion and protected CPU-cycle windows are not reset. A pending
CLKPR switch follows its existing two-edge model in the changing clock domain.

This is an ideal phase-continuous model, not a measured oscillator settling
waveform. Section6.4.1 warns about frequency steps over2% per cycle, CAL steps
over0x20, and NVM programming above nominal frequency+10%. Providing a table
does not prove those transitions electrically safe. Voltage, temperature,
metastability, glitches, transient settling and NVM failure probabilities are
not inferred. The table describes one selected operating condition. All128
entries and arbitrary provided transitions are executable digital fixtures;
there is no single-CAL restriction.

## Two explicit timestamp contracts

With a table, `device_physical_mode()` returns1 and one tick is exactly1ps,
`DEVICE_PS_PER_SECOND=10^12`. The fixed uint64 time coordinate is independent
of oscillator changes and CLKPR. It spans approximately213 days. Overflow
produces an explicit time fault. Digital/analog injection timestamps and output
events remain at their supplied integer picoseconds, even between CPU edges.
Clock edge deadlines round upward by less than1ps; retained numerator phase
prevents repeated rounding from accumulating drift.

`device_virtual_half()` remains the monotonic nominal divided-clock coordinate
used by component APIs. It advances as a time coordinate while actual domains
are gated in sleep/reset. Elapsed ns and watchdog pulses use independent exact
rational accumulators. Neither reads executed-instruction count or current Hz
as a wall-time scale. `device_clock.h` supplies checked multiply-add/divide and
phase-aware ceil calculations, with a native64-bit fast path and a full128-bit
limb fallback requiring no host imports or floating point.

| Physical API | Contract |
| --- | --- |
|`device_time_ps()`|Current uint64 physical time|
|`device_wait_until_ps(deadline)`|Service halted hardware; return **actual time**, which may stop early at readiness/reset|
|`device_inject_digital_ps/analog_ps(...)`|Queue exact physical timestamps, using the existing chronological queue|
|`device_pin_events_ps(count)`, `device_pin_state_ps()`|Physical pin records with `time_ps` timestamp|
|`device_startup_deadline_ps()`|Reset-ready time; UINT64_MAX while external RESET is held|
|`device_cpu_half_deadline_ps(n)`|Physical deadline of the next n nominal CPU half periods, using current frequency/phase|
|`device_cpu_halves_until_ps(deadline)`|Rounded-up relative half-cycle budget including retained phase;0 if deadline<=now|
|`device_next_sample_ps(start,frame,rate)`|`start+floor(frame*10^12/rate)`; independent of CPU frequency|
|`device_oscillator_hz()`|Current selected main-source Hz|

CPU deadline conversions assume the current rate. A runner must recompute after
clock writes and scheduled divisor transitions. An instruction may straddle an
audio/input deadline, but the C scheduler visits the event at its exact physical
timestamp. Audio must consume the uint64 physical pin timestamps and fixed-rate
sample deadlines, rather than deriving them from the current oscillator rate.
Absolute picoseconds beyond2^53 require BigInt/uint64 access and a bounded
relative-origin execution budget across any f64 boundary.

The physical ring has the same16-byte layout/capacity and no extra ring or copy.
`device_pin_event_ps_t` exposes `time_ps`; `device_pin_event_t` exposes
`base_half`. These are typed aliases of a common record with a timestamp union,
so C aliasing is well-defined. Common consume/clear APIs are unit-free.

Legacy `device_base_half`, wait/injection, pin accessors and startup-deadline
API retain their original initial half-oscillator-period meaning. They refuse
physical mode with `DEVICE_FAULT_CLOCK_CONTRACT`13 instead of reinterpreting
timestamps. Conversely `_ps` APIs refuse legacy mode. Existing default firmware,
clock configuration and fixed-frequency tests retain their original units.
CPU-cycle advancement and register APIs are shared by both contracts.

## NVM programming clock profile

Section6.4.1 says EEPROM/Flash timing uses the calibrated oscillator, but does
not specify a guaranteed CAL-dependent latency equation. A CPU clock table alone
cannot establish NVM programming behavior or justify inverse-frequency scaling.
Physical mode therefore requires an explicit programming profile before an
EEPROM write or Flash erase/write can start. Without it, programming produces
`DEVICE_FAULT_NVM_CLOCK_PROFILE`15/detail1 before changing memory or starting
an operation. Ordinary reads, ignored SPM commands and table configuration do
not manufacture programming results.

Configuration key18 `DEVICE_CFG_NVM_CLOCK_PROFILE` accepts0 (unspecified,
default) or1 (`DEVICE_NVM_CLOCK_FIXED_NS`). Key19
`DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ` supplies an explicit reference
frequency1..1,000,000,000Hz for profile1; zero is incomplete. Profile1 selects
the existing chosen nanosecond timings as an explicit fixture for the provided
table/reference condition, including when CAL changes. Already-active EEPROM
and Flash deadlines, progress, Flash generation and dirty pages are preserved
through clock changes. CPU/CLKPR changes never rescale elapsed wall time.

The reference records the programming-clock condition; this profile deliberately
does not apply a guessed ratio to latency. A measured per-CAL programming model
would be a separate profile. Fixed-ns latency under trimming is a chosen fixture,
not a silicon guarantee, especially outside the documented calibration envelope.
Legacy no-table fixtures keep their established NVM behavior without new options.

## Reset, sleep and validation

Fuse startup counts source periods using the reset factory frequency; watchdog
timeouts stay in their independent oscillator domain. BOD recovery stays in ns.
Explicit manual startup key12 retains its initial half-oscillator-period units
and converts once into physical duration. Power-down counts6 source CK before
the four additional CPU cycles; Idle/ADC modes retain the oscillator. The sleep
owner's exact-duration API rounds the complete four-cycle hold once, avoiding
four copies of a rounded individual cycle.

`device-clock.test.mjs` checks integer arithmetic against a BigInt oracle,
including1200 randomized wide multiplication cases. `device-osccal-runtime.test.mjs`
compiles the actual import-free board and verifies all128 nonlinear entries,
missing/configuration errors, phase and CLKPR retention, independent external/
128kHz sources, Timer0/ADC progress, exact input/pin timestamps, watchdog timing,
explicit NVM profiles, EEPROM/Flash completion, sample deadlines beyond2^53ps,
factory reset and fuse startup. Existing OSCCAL/BOD/sleep/scheduler fixtures
continue to exercise the unchanged legacy contract.
