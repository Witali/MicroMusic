# Inline provenance of retained native samples, 2026-11-01

The [replay evidence](native-inline-replay-20261101.json) joins verified
pre-Binaryen DWARF contexts to the existing kernel and long stereo captures.
All **10874 ticks**, including **5285 certain-interior ticks**, remain accounted
for. Legacy source budgets, reasons, lines, numeric function containers and all
work-window bounds match the retained reports exactly. Metadata segment count
changes from 15683 to 15841, including unmapped entries; this does not change
code or sampled work.

Production native bytes, compiler identity and engine defaults are unchanged.
Both scope artifacts and named capture modules preserve executable sections and
absolute offsets. No new workload, elapsed-time measurement or speedup is claimed.

## Certain-interior candidates

Same workloads as the [current sampling checkpoint](native-current-profile-20261030.md):
three 100M-instruction kernel windows and three 262144-frame stereo windows.

| Candidate class | Kernel | Stereo music |
| --- | ---: | ---: |
| Project leaf scope | 939 | 1386 |
| Support leaf scope | 6 | 10 |
| Unlabelled native position | 837 | 1276 |
| Other generated CPU/VM/setup work | 364 | 467 |
| Ambiguous/unresolved labelled context | 0 | 0 |
| Total | 2146 | 3139 |

Only the deepest unique project frame is counted for a labelled observation.
Overlapping incomparable chains stay ambiguous. Missing labels do not inherit
an earlier name; entry positions, source gaps and uncertain native generations
remain unlabelled. `other` is not a CPU-only duration.

| Project function | Kernel observations | Music observations |
| --- | ---: | ---: |
| `device_clock_ratio` | 82 | 157 |
| `at_half` | 86 | 94 |
| `avr_device_phase_clock` | 90 | 78 |
| `advance_half_until_ps` | 63 | 68 |

These are source-provenance candidates, not exclusive times or a reconstructed
dynamic call stack. Later Binaryen/V8 optimization can combine operations and
source-position predecessors cover uncertain intervals. Substantial unlabelled
native work remains; source ownership must not be extrapolated over it.

## Validation and next action

- All 80 focused checks pass: the previous 68 plus 12 inline dictionary/artifact
  checks. They cover disjoint window budgets, unknown/ambiguous contexts,
  source-coordinate bounds, private-field rejection and artifact identities.
- Three real CLI negative controls reject missing producer identities, shifted
  scope-module offsets and shifted named-capture offsets, even when altered
  digests/metadata agree with their supplied proof. None writes a success report.
- The ordinary CLI reconstruction mode still produces exactly the old kernel
  audit, with no inline extension. No new SDK process runs in inline replay mode.

Inspect conversion operands and native instructions at the surviving ratio and
phase-clock call sites before another optimization. The
[zero-product shortcut](clock-zero-20261030.md) remains rejected; more source
observations do not overturn its timing result. Preserve all timer/pin/IRQ/RESET
service and require full parity plus balanced uninstrumented timing for a change.
Exclusive subsystem timing, silicon validation and the **24/31** plan count
remain open/unchanged.
