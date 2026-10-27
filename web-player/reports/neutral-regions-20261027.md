# Working SREG copies omitted in flag-independent regions

The optional full ATtiny13A bounded-region emitter now omits its working SREG
snapshot/restore when the complete region neither reads nor writes a flag.
The initial SREG.I interrupt guard remains. BRxx, BLD and all flag writers keep
the conservative path; direct internal emitter callers keep its default too.
The public configuration, phase ABI and native runtime are unchanged.

This removes one direct byte load and one byte store per eligible accepted
region invocation. At the recorded ABI the body shrinks722 to704 bytes.
The focused fixture proves all other region bytes are identical. It covers
all256 incoming SREG values under both local policies, neutral instruction
forms, CPSE/SBRC/SBRS exits/two-word skips, public edits, IRQ/delay guards,
continuations, strict adjacent deadlines and RESET. Existing region checks
also cover clock-before-commit, ADC/WDT/Timer0, CLKI, packages and SPM.
See the [cookbook and official flag references](../../docs/avr-asm-cookbook/neutral-region-sreg.md).

## Generated size and functional verification

The verifier loads the exact historical compiler/region sources from
`da3f6504`, confirms unchanged support/native dependencies and compares36
catalog artifacts. Legacy, compatible full-device and ordinary resumable
outputs remain byte-identical. One bounded phase-local artifact changes:
`alicia`,296007 to295989 bytes. The other35 stay byte-identical. The synthetic
neutral-loop module also shrinks18 bytes with either phase-local policy.

**2560 checks pass:**2499 default and61 disjoint shared-tool checks. The57
focused cases are included in that default cohort. All native/runtime bytes
remain unchanged. Compiler identity is
`895a021183c067bd9533fee8f77e3eb3c4d38aa2d1cca430b5e9a7b8758f2804`.
The [machine-readable evidence](neutral-regions-20261027.json) pins sources,
baseline, native artifact, TAP hashes, output identities and timing samples.

Using the same current JS wrapper/native, old/new emitted CPU modules retain
exact PCM, requested pin events, registers/SRAM, EEPROM/Flash, IRQ frames,
native diagnostics and complete public state at sixteen256-frame checkpoints.
At4096 frames/48kHz, `rhythmic`, `lumiere-stereo` and `alicia` handle798/798/797
interrupts and1597/1877/1595 pin events respectively. A separate neutral-loop
workload retains exact state for131072 instructions; it has no IRQs or music
and does not establish real-time support.

## Timing screen and its limits

Four-label oldA/oldB/newA/newB ordering is balanced over eight fully serial
trials per workload. Every instance is fresh. Construction and equal warmup
are excluded. Music warms4096 frames through the nominal fuse startup before
4096 measured frames; the synthetic loop warms32768 instructions before131072
measured instructions. Each timed span excludes hashing, complete snapshots
and pin draining, while native pin/audio work remains inside. Every timed run
also retains exact same-span PCM/state/pins. This is coupled execution time.

Ratios greater than one favor the newer generated module; identity columns
compare equal versions. These are observed medians, not established speedups.

| Workload | Old identity | New identity | Old/new |
| --- | ---: | ---: | ---: |
| rhythmic | 1.051 | 0.965 | 0.961 |
| lumiere-stereo | 1.003 | 0.976 | 0.992 |
| alicia | 0.939 | 1.006 | 0.987 |
| neutral synthetic loop | 0.996 | 1.001 | 1.034 |

Identity ratios vary widely: individual bounds reach0.595–1.707 across these
controls. The screen does not establish an elapsed improvement or a slowdown
caused by this change. Retain this as a code-size/memory-operation reduction
under its precise condition; do not claim a general execution gain. Browser
throughput, underruns and exclusive subsystem costs were not measured here.

```text
node --test web-player/tests/*.test.mjs
node --test tools/avr-music-target-core.test.mjs tools/music-startup.test.mjs
node web-player/scripts/verify-neutral-regions.mjs --measure --output web-player/reports/neutral-regions-20261027.json --full-tap build/neutral-region-default.log --shared-tap build/neutral-region-shared.log
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

The native artifact is124505 bytes, SHA-256
`ad3e472582cbca5f7d0d57b7b17776c58a03f9b5f7eb89b55fda89ea84389fc7`.
No new host import, per-edge JavaScript callback, native rebuild, software
download or hardware session is part of this change. This is partial progress
on register traffic; the24/31 plan and seven original open items remain.
