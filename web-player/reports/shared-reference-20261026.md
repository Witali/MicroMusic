# ATtiny13A shared internal reference

The full native device now connects ADC, comparator and BOD reference demand
to one explicitly selected physical startup controller. Continuous owner
handoffs preserve readiness; loss of demand or qualified POR clears it.
External/watchdog resets retain a BOD-kept warm reference. BOD sleep disable
and independent recovery retain their existing rules.

The authority is [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections 7.3–7.4, 8.3.1 and 14.7. The [device contract](../native/devices/attiny13a/shared-reference.md)
documents explicit parameters, event order and analog limits. The controller
adds no instruction/edge JavaScript callback or host import.

## Behavior and compatibility

- ADEN requests the reference independently of REFS and stopped ADC clocks.
  ACBG requests it while software ACD is clear, including automatic comparator
  gating. BOD requests it unless its protected sleep-disable state applies.
- A shared deadline precedes a tied ADC sample or comparator clock stage.
  Publishing readiness never advances ADC; comparator publication uses its
  pre-edge cursor. Held CLKI permits startup but cannot fabricate ACO/ACI.
- An unavailable ADC sample diagnoses fault4/detail17 before a result or ADIF
  is published, for both internal and VCC references. Native admission rejects
  incomplete/incompatible profiles before touching caller memories.
- Current qualified POR controls power. Aggregate RESET and sticky MCUSR.PORF
  do not discard a continuously powered BOD reference. A POR added to an
  already-held RESET still invalidates it.
- Package v7/cache identities preserve the profile. Exact v1–v6 schemas remain
  supported; a genuine original v6 package executes its original native runtime
  with its independent comparator startup. Null profiles preserve old snapshots
  and behavior. Shared startup requires zero comparator-local startup.

## Validation

**2553 checks pass**: 2492 default checks and 61 disjoint shared-tool checks.
The first default run identified two test-stand linker dependency omissions;
the common fixture builder now recognizes normalized board paths and inlined
board fixtures. Both repaired groups and the final full run pass. No production
timing change was required for those test-stand failures.

New checks cover reference owner handoff, exact/adjacent sample boundaries,
odd-half samples, independently calculated rounded 9 MHz edges, held high/low
CLKI, PRADC, BODS Power-down with retained ADC/ACBG demand, warm external/WDT
reset and both orders of POR/RESET source handoff. These use synthetic explicit
startup values. The [machine-readable record](shared-reference-20261026.json)
pins passing TAP hashes, test sources and native identities.

```text
node --test web-player/tests/*.test.mjs
node --test tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
node web-player/scripts/verify-comparator-timing.mjs --feature shared-reference --out-file web-player/reports/shared-reference-20261026.json --full-tap build/bandgap-default-tests.log --additional-tap build/bandgap-shared-tests.log
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

The verifier compares native `d9e31cda` with the current native under the same
current JS wrapper. `rhythmic` and `lumiere-stereo`, each in verification and
bounded/phase-local policies, retain exact PCM, every requested physical pin
event, data/registers, EEPROM/Flash, internal CPU state and complete public
state across sixteen 256-frame blocks at 48 kHz. Each case handles798 interrupts;
pin counts are1597 and1877 respectively. This validates null-profile compatibility,
not execution speed or a real-time audio profile.

Current native WASM: **124505 bytes**, SHA-256
`ad3e472582cbca5f7d0d57b7b17776c58a03f9b5f7eb89b55fda89ea84389fc7`.
It has117 function exports plus memory, no host imports and fixed two-page
memory. Previous native:121019 bytes, SHA-256
`4183c8b0d0b71e720307d7d8dc7959b4c880ea78ec8286dbcbb719f944a93000`.
Compiler identity:
`63ca160c6e44322acf821f7d239e695c5c575d7f8eb916f2b8cf454414ecf1ae`.

The plan explicitly adds this newly identified requirement:24/31 complete,
with the seven original open items unchanged. No official simulator has been
executed and no silicon startup measurement has been made. BOD receiver startup,
analog noise/offset and voltage-dependent settling are not established by this
fixture. The official-host acquisition investigation remains separate.
