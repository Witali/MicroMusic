# A redundant compact guard that still helped one workload

The compact LPX sample path contains an error check immediately before six-bit
excitation clipping. It is logically redundant under the current decoder
contract, but removing it **was rejected for a measured speed regression**.
Production retains the check. Smaller generated code alone is insufficient
evidence for the requested no-speed-loss constraint.

## Reviewed invariant and equivalent C

`nextCore()` (the direct PWM `next()` body on AVR) rejects an existing error at
entry. At a sample boundary it checks the return values of `readFrame()` and
`readSubframe()`; successful compact readers return `!error_`. Interpolation,
optional bandwidth arithmetic and `pitchPredict()` do not read input or write
the error field. Compact `decodeCode()` only reconstructs/clips excitation and
updates pitch history. The noncompact branch reads entropy and keeps its error
check. Legacy sparse80 tail validation runs after sample arithmetic, returns
immediately on failure and is caught by the next entry guard on later calls.

This argument assumes exclusive, non-reentrant access to an instance and valid
object/storage lifetime. The playback IRQ accesses the FIFO, not the decoder's
error state. It is not a claim about memory corruption or concurrent mutation.
Revisit the invariant if a future arithmetic stage gains input/error side effects.

The proposed change is in the shared C++ source, so the explicitly selected C
backend and AVR implementation use the same logic. No new assembly or device
register definitions were introduced. Arithmetic selection still requires the
real supported architecture and explicit ASM enable; hardware input selection
remains independent.

## Native equivalence, measured rejection

The retained verifier privately restores/removes only the compact guard. It
performs 37,568 API trace comparisons, containing 23,839,440 API rows, across 16 explicit-C
configurations: v5 P4/P6 plus legacy v8 sparse80, and v9 P4/P6/15; standard/SRAM512
memory; pointer/count ROM cursors; per-sample/batched remaining counts. Inputs
come from public deterministic generators and fixed-seed mutations. Every begin
and next return, output including false-call output, error, sample count,
produced count, finished flag, sample rate and callback progress is compared.
Cases include failed begin, truncation, invalid metadata, callback EOF/out-of-range
returns, repeated false calls, source switches, partial tails and 64,000 samples.
Noncompact preprocessed source is byte-identical. These are API-equivalence
checks, not a speed result.

The guard-only candidate was then built for ATtiny88 / AVR25 without MUL at
16 MHz, avr-g++ 7.3, SRAM512, explicit ASM, product unroll2 and the reserved-register
standalone player ABI. FIFO32/prefill24 and the complete 38-cycle IRQ stayed
enabled. All 22 frozen historical workloads matched every PWM byte with zero
underruns. Every program was 6 B smaller and every observed stack was 3 B smaller.
Twenty-one workloads decoded faster; the public low15 example decoded slower.

| Candidate | Program excluding audio | Peak stack | Bread low15 mean cycles with IRQ | Chego 2k mean cycles with IRQ |
| --- | ---: | ---: | ---: | ---: |
| Production baseline `95346ea9` | 5605 B | 67 B | 1313.218502 | 1547.307943 |
| Remove compact error guard | 5599 B | 64 B | 1313.678296 | 1546.663914 |
| Remove guard and combine signed8 clipping | 5605 B | 64 B | 1313.279881 | 1546.250331 |

Guard removal regresses Bread by **0.459794 cycles/sample**. Combining clipping as
`if ((uint8_t)(decoded + 32) > 63) decoded = decoded < 0 ? -32 : 31;`
still regresses it by **0.061379 cycles/sample**, with no program saving. That
second candidate was screened only on the two named complete IRQ workloads;
its clamp identity was checked over all 256 signed8 values. Do not generalize
that cast-based identity to arbitrary signed16 inputs. Both candidates remain
rejected, with no arbitrary cycle tolerance. The cause is not established beyond
the compiler's changed generated code; no architecture-wide speed claim is made.

The [sanitized historical receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/compact-guard-measurements.json)
labels candidate/source hashes as historical and explicitly records that
production retains its guard. Measurements use simavr 1.6 with live timers/IRQs,
not a physical board. Mean cycles are not per-sample worst-case bounds.

## Reproduce

The host checks need Python 3.10+ and g++; NumPy and media are not
required. Normal CI uses one configuration, while the CLI defaults to all 16:

```sh
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_compact_error_guard.py
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_compact_error_guard.py build/guard-native
```

For the rejected AVR experiment, use the archived 22-case input/PWM directory
from `95346ea9` and the full native proof above. The AVR driver creates its own
source copy under the chosen ignored output, removes only the candidate guard
there and initializes the builder/verifier roots once before its worker pool.
Player, profiles, observer and the relative shared PWM header are copied too;
the original repository and pinned DFP stay in place. Active source is never
edited. The production source must match the reviewed `95346ea9` baseline so
unrelated changes cannot enter this comparison. Use a fresh output directory:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_compact_error_guard_avr.py \
  BASELINE_ADMISSION_DIRECTORY build/guard-avr \
  --native-receipt build/guard-native/summary.json --wsl Ubuntu --workers 4
```

The driver records production/candidate hashes separately, publishes a complete
report and exits unsuccessfully when any case is slower or larger. The retained
negative receipt binds the candidate sources actually measured; later harness
changes are reproduction tools, not retroactive measurement-source bindings.

This is original project analysis of shared C/AVR code. Existing vendor header
provenance/licensing and the player's reserved-register ABI remain unchanged.
