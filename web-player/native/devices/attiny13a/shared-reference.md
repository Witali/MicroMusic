# Shared internal reference

ATtiny13A's optional `bandgapProfile` connects ADC, comparator and BOD reference
demand in the native C/WASM device. It adds no JavaScript call per instruction,
clock or pin event. The simplified site engine keeps its current defaults.

The authority is [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 7.3–7.4, 8.3.1 and 14.7. The pinned original and its checksum are in
[`tools/downloads.json`](../../../../tools/downloads.json). Section 8.3.1 names
BOD, ACBG and enabled ADC as reference consumers, and requires startup before
using comparator or ADC output when BOD did not already keep it enabled.
This does not specify one universal startup curve or residual-charge behavior.

## Explicit profile

```js
const options = {
  resumable: true,
  oscillatorHz: 10000000,
  osccalHz: Array(128).fill(10000000), // Synthetic flat fixture, not calibration.
  fuseLow: 0x72,
  comparatorTimingProfile: {
    domain: 'physical-ns-v1', propagationNs: 200, bandgapStartupNs: 0,
  },
  bandgapProfile: { domain: 'physical-ns-v1', startupNs: 1000 },
};
```

Both values above are caller-selected examples. `startupNs` must be explicitly
provided as a uint32, including zero for an ideal fixture. Select physical time
through an OSCCAL table or external `clkiProfile`. The comparator physical
profile must be present with zero local startup; `bandgapStartupHalf` must also
be zero. This assigns startup to one controller and avoids counting it twice.
Comparator propagation and delivered-clock synchronization remain independent.
A null shared profile preserves every prior package/clock-counted fixture.

## Demand and lifetime

| Owner bit | Reference demand |
| --- | --- |
| 1 | ADEN is set, regardless of REFS or whether ADC clocks currently run. |
| 2 | ACBG is set and software ACD is clear. Automatic comparator gating in Power-down or PRADC does not clear this request. |
| 4 | BOD fuses enable the receiver and the protected sleep-disable sequence has not disabled it. |

Legal PRADC changes still require ADEN clear. A continuously enabled handoff
between owners preserves the original deadline or established readiness.
Reference readiness progresses in physical time during a clock hold or sleep.
It cannot publish ACO/ACI without the actual enabled synchronization edges.

This selected digital fixture discards readiness immediately when all demand
ends or qualified POR removes power. Re-enabling starts a fresh explicit delay;
no retained analog charge is inferred. With a power profile, current
`por_active` qualifies reference power. Aggregate RESET hold and sticky MCUSR
flags do not. External/watchdog reset clears software requests but preserves
continuous BOD demand and its warm reference. A POR added to an already-held
RESET still invalidates readiness.

BOD voltage detection, filtering and wake recovery retain their separate
configured model. Shared readiness does not shorten recovery, invent BORF or
establish the physical BOD startup transfer function.

## Event order and diagnostics

A shared physical deadline settles before a tied ADC sample or comparator
synchronization edge. Publishing ADC readiness does not advance its clock.
Comparator publication uses its already-serviced pre-edge cursor, then settles
new zero-delay raw work before delivering that edge. The same ordering covers
rounded 9 MHz edges, odd-half ADC sampling and initial-low CLKI alignment.

An ADC sample before readiness stops with peripheral fault 4/detail 17, before
publishing a result or ADIF. This applies to both internal and VCC REFS under
the section 8.3.1 startup restriction. The fixture does not fabricate an
unstable conversion value. Missing native startup configuration fails before
caller data/Flash/EEPROM are touched. Existing comparator errors retain their
diagnostic precedence when both profiles are invalid.

Package v7 records the profile and validates all seven native capabilities and
their signatures. Readers retain exact v1–v6 schemas; a genuine retained v6
package still executes its original native comparator runtime. Cache identity
includes the new configuration. Selected-profile `state().bandgap` exposes
`active`, `powered`, `ready`, `owners` and unsigned `deadlinePs`; UINT64_MAX
means no pending event. Null-profile snapshots omit the property.

## Evidence and limits

The controller, consumer seams, admission, package and actual generated-CPU
lifecycle checks cover continuous handoff, cold acquisition, sleep/BODS,
PRADC, warm reset, POR and held CLKI. Independent arithmetic places reference
readiness one picosecond before, on and after the ADC sample. Active-IRQ music
comparisons check null-profile PCM, pins and complete state against the previous
native artifact. See the [retained integration evidence](../../../reports/shared-reference-20261026.md).

These are software and explicit-profile checks. No official simulator session
or silicon reference measurement has been executed. Noise, input offset,
metastability, voltage-dependent startup and calibration remain unmeasured.
