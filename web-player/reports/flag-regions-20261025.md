# Rejected guarded inter-block SREG optimization

The prototype is rejected and removed from production. It is correct under the
tested model, but does not demonstrate a speed improvement and increases CPU
module size. The unchanged generator/runtime are restored to `ae265f7`; native
WASM remains SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.

## Candidate

The candidate combines two adjacent register-only blocks, up to64 instructions,
only when the combined backwards liveness plan removes more flags than their
separate plans. The I bit never changes in these blocks. Full SREG remains live
at the combined exit. Original block entries remain callable for external entry
and short instruction budgets. Every count, event, physical deadline and retired
counter guard covers the entire region. Guard rejection calls the original
first block; after native clock work starts, reset/fault/WAIT retains the existing
fail-closed exit rather than replaying a block. I/O, memory and branch instructions
are not combined. No phase-local or Binaryen optimization is mixed in.

This couples flag elimination with fewer native phase-clock/retirement calls.
It cannot isolate the cost of SREG arithmetic alone. It adds a function per
region and additional guard/fallback work; statically fewer flag bits do not
establish a speedup. In particular, flags dead for a later AVR instruction may
still be observable through a public instruction limit or physical deadline.

## Activation and correctness

An untimed trace runs one million retired instructions from each of three
firmwares with idle acceleration disabled. Returned block counts and final
phase PCs identify actual fused execution, without adding runtime counters to
the generated WASM. The original public runner reaches matching bounded
instruction endpoints; full architectural/diagnostic state and pin transitions
are compared at11698 checkpoints.

| Firmware | Regions | Accepted combined blocks | CPU bytes before/after | IRQs |
| --- | ---: | ---: | ---: | ---: |
| rhythmic | 4 | 1 | 387264 / 391904 | 5497 |
| lumiere-stereo | 6 | 1789 | 391150 / 397386 | 5543 |
| hq4-chego-tiny | 6 | 15614 | 406944 / 411703 | 5712 |

These counts describe the measured prefixes, not whole-song reachability.
Some static regions lie in decoded data and were not reached. Existing
instruction/table fallback remains necessary for arbitrary dynamic targets.

The candidate passes1662/1662 Node checks. Thirteen new cases include actual
fusion, carry/chained-zero dependencies across the old boundary, every public
instruction budget, entry into the second block, half-phase/1ps observations,
timer/comparator/pin IRQs, RESET, protected windows, CLKPR, pending IRQ/delay,
active continuation, retired-counter overflow, phase-local composition and
loading/executing a package containing the new dispatch table.

All13 standard workloads retain exact PCM/state/pins in26 parity runs and168
checkpoints, including internal/external20MHz, /1,/256 and active ADC. Default
translations are byte-identical to the historical generator from `ae265f7`.
The raw reports record actual firmware IDs, hashes and the old HQ4 alias.

## Performance decision

One unchanged native Module and shared CPU Modules within identical-binary pairs
use fresh instances/memories. Eight balanced four-label trials and four warmups
per label run with GC before execution, outside the timer. Construction,
generation, compilation, snapshots and hashing are excluded. Ratios above one
favor the candidate.

| Case | Old identity median | New identity median | Cross median | Faster trials |
| --- | ---: | ---: | ---: | ---: |
| lumiere-stereo-physical | 1.014 | 0.961 | 0.993x | 4/8 |
| hq4-chego-auto-physical | 0.999 | 0.953 | 0.958x | 2/8 |

The screen retains64 timed runs,32 discarded warmups and1152 exact checkpoints.
Identity pairs remain noisy, so these results do not prove a causal slowdown;
they also provide no basis for accepting a speedup. Whole modules grow1.2–1.6%.
The remaining performance matrix was not run. `complete:true` refers to the
selected two-case screen, not full performance acceptance or browser behavior.

## Restoration and reusable results

Production compiler/runtime sources are restored exactly; [restoration hashes](flag-regions-20261025/restoration.json)
pin that assertion. Three retained regression tests verify full SREG after
public instruction limits/external entries, half-phase/1ps observations and IN
of SREG. They compare ordinary block execution with the unchanged individual
instruction path. The restored full suite passes1652/1652, zero skips (85.43s).

The benchmark's historical-generator loader now resolves its phase-local module
dependency explicitly and verifies that it is unchanged. A real CLI check
against `ae265f7` exercises this path. Separately, the SDK driver's help confirms
that its native Clang pipeline already enables wasm-opt by default; documentation
now distinguishes that driver behavior from an additional generated-CPU pass.

Next experiment: constant/short-sequence folding inside existing guarded blocks,
preserving every visible register/SREG exit and original cycle count, without
adding regions or native guard calls. Larger control-flow regions need a distinct
design and evidence. The hardware-support plan remains21/30, with nine open items.

## Reproduction

```sh
node web-player/reports/flag-regions-20261025/rebuild-candidate.mjs
node web-player/reports/flag-regions-20261025/verify-evidence.mjs
```

The isolated helper reproduces all13 recorded CPU binaries byte for byte in an
ignored build directory, using the archived candidate generator and historical
native runtime. It does not install the rejected implementation. The complete
candidate sources, patch, trace/harness/test sources, [activation trace](flag-regions-20261025/activation.json),
[parity matrix](flag-regions-20261025/validation.json),
[timing screen](flag-regions-20261025/screen.json) and both full-suite logs are
retained. `fuseFlagBlocks` is an archived prototype setting, not a current option.

Primary semantics: [Microchip AVR manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny13A datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
Existing device definitions and flag equations remain unchanged.
