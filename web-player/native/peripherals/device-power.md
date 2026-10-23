# Optional physical supply profile

The device scheduler connects the standalone [power-reset observer](power_reset.md)
only when explicitly selected before initialization. Existing fixed-clock and
physical-clock profiles keep supply monitoring disabled by default. The new
profile requires the fixed1ps time contract, selected by an explicit OSCCAL
frequency table even if that table describes a constant frequency. It does not
claim arbitrary analog or complete silicon behavior.

## C configuration and inputs

Call `device_configure_power(field,value)` before `device_init`. Field0 is
enable0/1; all fields1–9 must have been explicitly set when enabled. Field0=0
clears selection and supplied-field tracking. Configuration order is otherwise
independent. The device copies the configuration at init; later setter calls
configure a future init rather than change a running observer.

| Field | Named constant | Units |
|---:|---|---|
| 0 | DEVICE_POWER_ENABLE | 0 or 1 |
| 1 | DEVICE_POWER_POR_ASSERT_UV | Positive int32 microvolts |
| 2 | DEVICE_POWER_POR_RELEASE_UV | Positive int32 microvolts, >=field1 |
| 3 | DEVICE_POWER_BOD00_UV | Positive int32 microvolts |
| 4 | DEVICE_POWER_BOD01_UV | Positive int32 microvolts |
| 5 | DEVICE_POWER_BOD10_UV | Positive int32 microvolts |
| 6 | DEVICE_POWER_HYSTERESIS_UV | Nonnegative int32 microvolts |
| 7 | DEVICE_POWER_FILTER_NS | uint32 nanoseconds |
| 8 | DEVICE_POWER_RECOVERY_NS | uint32 nanoseconds |
| 9 | DEVICE_POWER_FLASH_PROGRAM_MIN_UV | Positive int32 microvolts |

No values are silently copied from typical-characteristics tables. All BOD
levels must fit their hysteresis range. Nanoseconds are converted once to1ps
ticks. Field9 selects the boundary of a **declared Flash programming profile**;
it is not asserted to be a measured chip-specific failure threshold. EEPROM's
separate1.9V uncertainty rule comes from the official erratum. Field8 supplies
recovery for this profile; the older config15 `BOD_RECOVERY_NS` continues to
serve profile-off operation.

Existing config3 selects initial VCC. Zero is accepted at init only with an
enabled supply profile. Initialization represents an initial VCC0 condition
followed by an immediate step to that configured value. At nonzero sufficient
VCC this produces one initial POR without a pending CPU reset request; at VCC0
reset remains held. Subsequent `device_reset` calls retain current VCC, the
observer's source levels and deadlines, queued inputs and calibration table.

`device_inject_vcc_ps(at,microvolts)` appends a VCC input to the same128-entry
chronological queue used by digital and analog inputs. VCC must be nonnegative
int32; `UINT64_MAX` is reserved and invalid. Only a selected supply profile
accepts this API. Same-time deadlines and peripheral sampling occur before
queued inputs, in insertion order. Current-time inputs apply immediately
through the same path. `device_vcc_microvolts` reports current supply and
`device_power_enabled` reports the latched mode.

## Reset and wake behavior

The observer aggregates POR, BOD, already-qualified PB5/RESET, and a WDT reset
pulse. I/O/peripheral state resets immediately at the ASSERT timestamp; the CPU
bridge receives `reset_requested` and abandons later instruction effects.
`device_reset` acknowledges an already-applied peripheral reset instead of
applying it twice. Additional HOLD causes update MCUSR/WDE without a second
CPU reset request. POR clears earlier non-POR causes as documented. The
observer remains alive throughout the hold.

The WDT raw pulse lasts one undivided source CK, using the reset/factory clock
profile. Its release has a scheduler deadline independent of CPU execution.
The fuse startup owner starts6CK+14CK/SUT only after the **last** source releases;
the observer's `timeout_ticks` is zero. The older WDT-pulse addition inside
startup is disabled for this path, so the pulse and timeout are charged once.
With fuse startup disabled, the explicit digital profile still models the one-CK
WDT pulse. The watchdog oscillator and adequate-voltage NVM continue during
reset; the watchdog counter remains reset during reset hold/startup.

BODCR's existing protected CPU-cycle sequence remains its register owner.
Successful Power-down entry passes its authorized disable to the observer.
An eligible wake re-enables BOD and starts recovery concurrently with oscillator
startup; the CPU waits for the longer interval, then the normal four wake
cycles. Recovery gates execution without pretending to reset every peripheral
or reset the watchdog counter. A qualified low-VCC wake can assert reset before
recovery ends. See the observer document for prequalification, equality and
analog-startup conventions.

## Analog supply and NVM

A VCC input updates the ADC supply reference and the voltage corresponding to
logical-high pins. Explicit analog pin injections retain their absolute
microvolt values. The configured bandgap remains an explicit reference profile;
the model does not fabricate its voltage/temperature dependence, I/O analog
threshold curves or behavior outside electrical ratings. Reset uses current
VCC rather than restoring config3's initial supply.

EEPROM programming starting below1.9V, or any below1.9V span while busy,
latches `DEVICE_FAULT_NVM` with detail128. Flash programming outside the
selected field9 boundary latches detail256. Checking occurs after an accepted
programming command and at supply mutation, before later completion. The
[NVM uncertainty guard](nvm-voltage.md) freezes the affected pending operation
through every implicit advance/read/reset path. It preserves the last known
bytes and pending metadata, without treating them as a guaranteed physical
result. Recovery of VCC or CPU reset does not clear this diagnostic; a fresh
`device_init` begins a new simulation image. Adequate-voltage programming
continues across normal reset as documented.

Primary references are DS40002307A §§7.2/7.5.1,8.1–8.2,8.5.1,18.5 and
DS80000857A2.2.1, linked in the observer and NVM documents. Exact source/CPU
edge ordering and typical analog parameters remain selected digital
conventions, not measured guarantees for every physical chip.

## Verification and linking

`tests/device-power.test.mjs` compiles the board with its observer and no host
imports. It covers initial cold supply, exact mid-span reset, BOD filtering,
hysteresis, aggregate release/SUT, WDT pulse width, BODS/wake recovery, ADC/GPIO
supply propagation and persistent EEPROM/Flash uncertainty. Existing standalone
board tests run with the supply profile disabled. The normal runtime build must
link `power_reset.c` and expose the new C APIs through its own bridge; these
files do not change bridge, JavaScript, package serialization or UI selection.
