# Empty wake-delay evaluation: not retained

Conditionally evaluating two unused wake delays preserves tested behavior but
does not establish a sufficient execution-speed benefit. **Production C/WASM,
ABI, compiler/cache identity and defaults remain at `9e8909ff`.** Six new sleep
boundary regressions and reusable isolated experiment tools are retained. The
device plan remains **24/31 complete, seven open**.

The [technique and official references](../../docs/avr-asm-cookbook/empty-wake-delays.md)
explain why only fixed, non-faulting delay calculations can be omitted when no
source requests wakeup. Peripheral service and the sleep cursor still advance.
Configured startup/recovery evaluation remains in its original position, so
startup overflow cannot disappear during empty polls. This is a source-level
experiment, separate from the previously rejected ratio arithmetic guards.

## Build and correctness

Original native: 124590 bytes, SHA-256
`244b3d3da85ff6cd065e6b105b18d26d8ae07e6615802d77f23a123338209c98`.
Candidate: 124589 bytes, SHA-256
`ba2bc55c081ac9064c4806176da72ee2600eea3614eff19d060802eafacfbd7d`.
Only body 160 changes among 218 bodies, from 1763 to 1762 bytes. A control build
reproduces the original module byte-for-byte; both versions retain 117 function
exports, zero imports and fixed two-page memory. No production source or native
artifact was swapped during this experiment.

All **six baseline and six candidate checks** pass against the real C board
policy. They cover empty-poll cursor/state preservation, exact first-wake rounding
after source/divider changes, BOD recovery, startup overflow without a request,
non-waking sources, reversed time and actual-wake deadline overflow. Software
frequency extremes exercise admitted arithmetic bounds; they are not measured
ATtiny13A clock profiles.

All **16 equal-policy workload comparisons** pass with byte-identical generated
CPU modules and ABI. They cover compatible/physical music, direct execution,
CLKI /1 and /256, and active ADC/watchdog controls. Recorded PCM, complete public
and diagnostic state, GPR/SRAM/Flash/EEPROM, IRQ frames and retained tail pins
agree. The active ADC/watchdog cases assert actual conversions/ISR service.
This is not complete waveform or hardware/underrun qualification.

## Two serial timing series

Windows/Ryzen 5 5600X, Node 22.22.3 / V8 12.4.254.21-node.56. Both versions
use the same explicit physical/resumable, bounded-region and phase-local policy.
This is not the conservative verification preset. Four-label Williams order,
eight trials and four full-workload warmups per label retain old/old and new/new
identity controls. CPU construction/compilation, snapshots and hashing remain
outside execution timers. Tests, compilers and profilers did not run alongside
timing; host load, frequency, GC and JIT tiering remain uncontrolled.

The first series uses 12000 music frames at 48 kHz and one million direct
instructions. Confirmation uses 24000 frames and ten million instructions;
the short first kernel runs were only about 12 ms. Ratios above one favor the
candidate. These are coupled execution ratios, not exclusive subsystem costs.

| Case | First old/new | Confirmation old/old | Confirmation new/new | Confirmation old/new | Faster pairs, first / confirmation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rhythmic physical | 1.075 | 0.966 | 1.044 | 1.016 | 8/8 / 6/8 |
| Lumière stereo physical | 1.053 | 1.067 | 0.992 | 1.025 | 5/8 / 6/8 |
| HQ4 physical | 1.025 | 0.977 | 0.978 | 1.004 | 5/8 / 5/8 |
| Internal direct | 0.903 | 1.003 | 0.993 | 1.039 | 2/8 / 6/8 |

The stronger initial Rhythmic result weakens in confirmation; the kernel result
changes sign. Identity-pair ranges are broad, including approximately 0.705 to
1.216 in confirmation. These data do not establish a useful gain or a general
regression. No further runtime adoption, full candidate suite or wider timing
matrix was justified after this gate failed.

The retained data include **256 timed runs, 128 warmups and 5259 exact checkpoint
comparisons**, plus the sixteen old/new correctness pairs. The
[JSON evidence](empty-wake-20261101.json) retains individual times, recomputed
ratios, exact output/source hashes, build proof and TAP digests. Raw originals,
C copies and binaries stay ignored under `build/empty-wake-20261101/`. Existing
registered SDK inputs were reused; no external download or installation occurred.
Two real CLI corruption controls reject a changed elapsed-time ratio and changed
PCM hash; neither creates a success report.
No official simulator session or silicon measurement ran. The virtual-event
10 ns requirement is separate from host elapsed-time measurement.

## Reproduction

From the recorded source revision, reconstruct without editing production:

```text
node web-player/scripts/rebuild-empty-wake.mjs --out-dir build/empty-wake-20261101
node web-player/scripts/benchmark-runtime-controls.mjs --baseline-ref 9e8909ff --candidate-root build/empty-wake-20261101/shadow --change-set empty-wake --bounded-regions --phase-locals --validate-only --out build/empty-wake-20261101/parity.json
```

For each timing series use the same baseline, candidate-root, change-set and
policy arguments, with `--case rhythmic-physical --case lumiere-stereo-physical
--case hq4-chego-auto-physical --case kernel-internal-20m-div1-direct`. The first
uses `--frames 12000 --instructions 1000000 --out build/empty-wake-20261101/screen.json`;
confirmation uses `--frames 24000 --instructions 10000000 --out
build/empty-wake-20261101/confirmation.json`. Run serially without other tests
or profiling. `--bounded-regions`/`--phase-locals` apply only to resumable cases;
existing default benchmark policies remain available.

Run `node --test web-player/tests/device-wake-delays.test.mjs` for the baseline.
For the candidate, set PowerShell `$env:MICROMUSIC_WAKE_SOURCE` to
`build/empty-wake-20261101/candidate-device.c`, run the same tests, then remove
that environment variable. Save their complete TAP as
`build/empty-wake-baseline-tests-20261101.tap` and
`build/empty-wake-candidate-tests-20261101.tap`. The override must remain inside
`build/`; ordinary tests use production sources.

Audit the retained raw captures without another timing run:

```text
node web-player/scripts/verify-empty-wake.mjs --output build/empty-wake-evidence-replay.json
```

Native runtime and all 41 compiler source inputs remain unchanged. The prior
2862/2862 full runtime checkpoint belongs to unchanged production; it was not
rerun for this rejected prototype and its new diagnostic/regression tooling.
