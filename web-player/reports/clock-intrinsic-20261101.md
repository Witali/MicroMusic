# Checked clock overflow: not retained

Replacing the clock ratio helper's division-based overflow guard with Clang
checked multiply/add builtins preserves the tested arithmetic but establishes
no useful speedup. Production C, native WASM and build manifest remain exactly
at `103ca59a`; the candidate exists only under ignored `build/`.

The [cookbook](../../docs/avr-asm-cookbook/checked-clock-overflow.md) explains
the equivalence and links the official builtin contract. The original
zero-divisor guard, wide fallback, event servicing and clock boundaries remain.
No AVR instruction lowering, SREG handling or device register definition changes.

## Artifacts and correctness

Baseline: 124614 bytes, SHA-256
`b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`.
Candidate: 124624 bytes, SHA-256
`19b325dc8a79730a7c9cb197879b838ff6f5f6d61312aed9bd830529cc438e1f`.
A fresh isolated reconstruction reproduces both binaries exactly using the
registered Emscripten 6.0.12 SDK, Clang 24 and the manifest's original flags.
Seventeen C sources, 117 function exports, no imports and fixed two-page memory
remain unchanged. Of 218 bodies, only `duration` (index 154, 577 to 577 bytes)
and `ratio` (155, 522 to 532) differ. Their static `i64.div_u` counts change
from 4/5 to 4/4; both versions already have zero `i64.rem_u` in these bodies.
Manual quotient/remainder reuse would duplicate an optimization already applied.

Baseline and candidate each pass all seven focused clock checks. A standalone
candidate probe passes **5375** independent BigInt comparisons: 375 boundary
combinations and 5000 deterministic uint64 cases, including zero divisor,
wide products, quotient overflow and preservation of failed-call outputs.
The sixteen-workload equal-policy matrix passes all old/new comparisons with
identical generated CPU bytes/ABI, PCM, architectural/diagnostic checkpoints,
Flash/EEPROM/SRAM/interrupt state and retained tail pins. It covers physical
and compatible music, direct execution, CLKI /1 and /256, ADC and watchdog.
This is software parity, not a complete physical waveform observation.

## Timing screen

Node 22.22.3 / V8 12.4.254.21-node.56 on Windows, Ryzen 5 5600X. Music runs use
12000 frames, CLKI 1200 frames at 48 kHz, and direct execution one million
instructions. Each case has eight balanced four-label trials and four
full-workload warmups per label. Old/old and new/new are identity controls;
old/new elapsed-time ratios above one favor the candidate.

| Case | Old/old median | New/new median | Old/new median | Candidate faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Rhythmic physical | 0.994 | 1.043 | 1.011 | 4/8 |
| Lumière stereo physical | 1.004 | 1.030 | 0.968 | 3/8 |
| CLKI 20 MHz /1 | 1.006 | 1.009 | 0.991 | 3/8 |
| Internal 20 MHz /1 direct | 0.978 | 0.974 | 0.970 | 2/8 |

The screen completed **128 measured runs and 64 warmups**. Together with the
parity matrix it compares **1298 exact checkpoints**. Identity controls vary
materially; neither a useful speedup nor a general regression is established.
No longer timing confirmation or full candidate runtime suite was run after
this gate failed. Tests, compilers and profilers did not run alongside timing;
host load, clock frequency, GC and JIT tiering remain uncontrolled. No browser
real-time, buffer-underrun, silicon or exclusive-subsystem-cost claim follows.

## Reproduction

The [JSON evidence](clock-intrinsic-20261101.json) retains individual measured
durations and warmups, recomputed ratios, workload/output/source/TAP hashes,
the reconstruction proof and disassembly counts. Original captures, candidate
inputs and TAP files are under ignored `build/clock-intrinsic-20261101/`.
The reusable builder needs Git history and the already registered SDK:

```text
node web-player/scripts/rebuild-clock-intrinsic.mjs --out-dir build/clock-intrinsic-reconstruction-20261101
```

The collector additionally needs the retained raw captures and TAP files:

```text
node web-player/scripts/verify-clock-intrinsic.mjs --output build/clock-intrinsic-evidence-replay.json
```

`benchmark-runtime-controls.mjs --candidate-root build/.../shadow` now accepts
isolated generated inputs while keeping host JS/firmware fixed. It rejects
roots outside a nonempty descendant of `build/`. The pinned producer is
`2fb13f82`; no production artifact swap is needed. The initial standalone probe
needed a delay wrapper and a fixture-path correction before its passing run;
these were harness issues, not weakened model assertions. No download or
installation occurred. The plan remains **24/31**, with seven items open.
