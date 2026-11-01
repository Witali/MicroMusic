# Firmware-level PWM boundary checks, 2026-11-01

All **144 new firmware cases** and the complete **3025/3025** test suite pass.
Across **72 conservative/optimized policy pairs**, complete recorded state,
GPR/I/O/SRAM data and pin traces agree. All **408 selected-pin events** match
the independent timing formulas exactly, while **264 IRQs** are serviced.
No runtime correction was needed. Production native/compiler/cache sources and
defaults remain unchanged from `87173ce8`; the plan stays **24/31, seven open**.

## What is checked

The [fixture](../tests/fixtures/attiny13a-pwm-boundaries.mjs) executes actual AVR
instructions through the connected CPU, bus, Timer0, GPIO and native pin buffer:

| Family | WGM | Variable compare channels | OCR cases |
| --- | --- | --- | --- |
| Fixed TOP=255 | 1, 3 | OC0A and OC0B | 0, 127, 255 |
| Variable TOP=7 | 5, 7 | OC0B; OC0A remains the constant TOP control | 0, 3, 7 |

Each combination runs normal/inverted COM, internal/asymmetric external CLKI
and both CPU policies. The other channel is connected and checked as a constant
extreme. Register addresses, masks and vector indices use the pinned official
Microchip definitions. Non-PWM FOC preloads the required latch level; no TCNT
write is used. The final OUT starts Timer0 at a known boundary; the fixture
checks zero compare flags from the preloading sequence. Timer overflow interrupts execute a real
INC/RETI ISR during all three observed PWM periods.

Internal timing is an ideal 1 MHz software calibration fixture, factory CAL
index zero, zero fuse-startup delay and CPU/Timer0 /1. It is not a measured RC
curve. External CLKI has 300000 ps high and 700000 ps low, zero-seeded digital
phase and a declared 5 ms horizon. Pin observations include both OC0A and OC0B;
selected outputs must stay driven and free of contention. Constructors, firmware
generation and API calls are outside any performance claim; no timing benchmark
was performed.

Verification uses `fastIdle:false`, `fastBlocks:false`, all flags and the full
phase context. The optimized comparison also keeps fast idle off, enabling
bounded regions, phase locals, flag optimization and optional SRAM blocks.
Native peripherals process their original event boundaries in both policies.

## Reference and evidence

The reference generator uses closed-form periods and compare offsets, not a
call into the C timer or another emulator. The
[cookbook](../../docs/avr-asm-cookbook/pwm-firmware-boundaries.md) identifies the
official sections and the retained digital compare-pulse interpretation. It
also records the visual Table 11-8 check. Stable OCR values are loaded before
entering PWM; no buffer transfer during a running waveform is asserted here.

[JSON evidence](pwm-boundaries-20261101.json) retains every selected-pin event,
firmware/data/state/expected-trace hashes, final state, native and compiler source
identities and both TAP digests. The collector reruns all cases, checks every
edge against its formula and then compares all 72 full-state/data/trace pairs.
The ordinary test runner independently completed the 144 case assertions.
Native remains 124590 bytes, SHA-256
`244b3d3da85ff6cd065e6b105b18d26d8ae07e6615802d77f23a123338209c98`;
compiler/cache identity remains
`6dff8aef30a8847d4abb3dad56d0d12d52889ac034c9cab42c13611121545a5d`.

These are software/reference-formula results. They do not establish physical
10 ns accuracy, measured oscillator calibration, internal CPU phase timing,
dynamic TOP transfer precedence, WGM5/TOP0 or real-time audio/underrun support.
No official simulator session ran. Existing registered SDK/document inputs were
reused, with no new download or installation. The rendered official table and
raw logs remain ignored under `build/`.

## Reproduction

```text
node --test web-player/tests/attiny13a-pwm-boundaries.test.mjs
node --test web-player/tests/*.test.mjs
node web-player/scripts/verify-pwm-boundaries.mjs --test-tap build/pwm-boundaries-20261101.tap --full-tap build/pwm-boundaries-full-20261101.tap --output build/pwm-boundaries-evidence-replay.json
```

Redirect complete stdout/stderr from the first two commands to the TAP paths
shown in the third. The full run passes 3025 tests with zero failures, skips,
cancellations or TODOs. Use the retained source revision to reproduce its
native/compiler identities; the collector rejects another production version.
