# Physical comparator propagation and clocked synchronization

The full ATtiny13A runtime now accepts an explicit physical comparator timing
profile. Analog propagation and reference startup run on independent ps
deadlines, including held CLKI and CLKPR changes. ACO/ACI, ADC triggers and CPU
interrupts still follow delivered enabled rising edges. Legacy half-clock
fixtures retain their previous interpretation.

The source distinction is specified by [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
section 13.2.2/page 86 and Table 18-7/page 127. Delays depend on supply/input
conditions; tests use caller-supplied synthetic values and establish no silicon
calibration. The [device contract](../native/devices/attiny13a/comparator-timing.md)
documents configuration, phase conventions and remaining analog limits.

## Integrated behavior

- Raw analog completion runs during known clock holds; it cannot itself set
  ACO/ACI or start an ADC conversion. Both actual synchronization stages remain.
- Rounded 9 MHz edge ties use the rational residue bound rather than assuming
  zero residue. Exact/adjacent 1-ps stops distinguish pre/post-edge input.
- Initial-low CLKI's first real rise can align half epoch zero. A once-only
  arming hook samples that edge without changing shared counters or sampling it
  twice. Pre-edge VCC/RESET/PB3 changes settle before clock delivery.
- RESET, ACD, Power-down and PRADC retain their gates and cancellation rules.
  Tests exercise a real generated ISR, ADC triggering and PCINT wake.
- Native init rejects missing delay fields, mixed domains and nonphysical
  profiles before touching caller memory. Reversed time and overflow fail
  explicitly; retained original runtimes reject unsupported capability.
- Package v6 and persistent-cache keys preserve the profile. Readers retain
  versions 1–5, including a genuine v5 continuation fixture. The browser runtime
  URL and generated compiler identity were refreshed.

## Validation

**2442 checks pass** across the recorded suites. Default test discovery ran
2371 checks; the additional suite runs 61 shared-tool checks and ten new native
admission/IRQ/sleep checks added after that discovery. The cohorts are disjoint.
The [machine-readable evidence](comparator-physical-20261026.json) records both
TAP hashes, current test-source hashes and baseline/current native identities.

```text
node --test web-player/tests/*.test.mjs
node --test tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs web-player/tests/device-comparator-profile.test.mjs web-player/tests/attiny13a-comparator-irq-sleep.test.mjs
node web-player/scripts/verify-comparator-timing.mjs
```

The verifier compares the retained native baseline from `23ef393d` with current
default-mode execution using the same current JS wrapper. Two real firmwares,
each in verification and bounded/phase-local policies, retain exact PCM, full
physical pin traces/timestamps, SRAM/registers, EEPROM/Flash and complete public
state across sixteen 256-frame blocks. Each case handles **798 interrupts**;
the four cases use 4096 frames at 48 kHz. This isolates native default-mode
compatibility; it is not a performance benchmark.

Current native WASM is **121019 bytes**, SHA-256
`4183c8b0d0b71e720307d7d8dc7959b4c880ea78ec8286dbcbb719f944a93000`.
It has no host imports, 110 function exports plus memory, and fixed two-page
memory. The retained baseline is 119010 bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
Compiler identity is
`194347459330b5d07e70fe857431359b05a09d7f89f0ba0aaaa6fd89dd625e50`.

The seven original open checklist items remain open: this adds software/profile
coverage, with no official-simulator execution, physical timing measurement,
debugWIRE completion, throughput or real-time audio claim. The manufacturer
host acquisition failure is registered separately; no installer was executed.
