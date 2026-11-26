# LSF packing gate and unchanged-LPX CPU investigation

The selected baseline is current LPX at production revision `24fd9416`, whose
source is unchanged in task branch `codex/lpx-lsf-groups`. Following the user's
instruction to stop a branch that loses compression, this study checks packing
before implementing another decoder. **No new codec or faster decoder was
admitted.** Existing LPX retains the best measured quality/size result here.

## Identical inputs

The corpus is the previous comparison's four public repository recordings,
each in current P4/P6 with calls=4: `chego`, `otvechaesh`, `vinni` and `bread`.
The source PCM, native LPX, analysis models and decoded PCM are verified against
their retained hashes. The first three sources use the same previously
scalar/SciPy-cross-checked 7.5→8 kHz resampling; bread is originally 8 kHz.
No fitted gain/delay or source-specific decoder table is introduced.

`prepare_inputs.py` can regenerate these inputs or copy a local cache only after
checking every pinned source/model/LPX/PCM digest. Cached metrics are not trusted:
the current rebuilt native tool validates decode identity and recomputes them.
Original cached encoding provenance and the current validation probe identity
are recorded separately. Media, firmware and temporary models stay in ignored
`build/`.

## Exact packing result

| Complete file | Current LPX | Adaptive native/group minimum | Forced groups, calculated |
| --- | ---: | ---: | ---: |
| chego P4 | 522 B | 522 B | 615 B |
| chego P6 | 937 B | 937 B | 1,028 B |
| otvechaesh P4 | 545 B | 545 B | 622 B |
| otvechaesh P6 | 671 B | 671 B | 753 B |
| vinni P4 | 1,200 B | 1,200 B | 1,411 B |
| vinni P6 | 2,239 B | 2,239 B | 2,466 B |
| bread P4 | 994 B | 994 B | 1,170 B |
| bread P6 | 1,479 B | 1,479 B | 1,652 B |
| **Total** | **8,587 B** | **8,587 B** | **9,717 B (+13.16%)** |

Across 386 frames (383 changed spectra and three repeats), native spectral fields cost 10,146 bits; forced grouping
costs 19,204 bits. Native Rice wins every adaptive decision. The grouped path
selects mostly exponent zero: 409 nonzero-width groups at exponent 0 and only
20 at exponent 1. The indices are already on compact 5/6-bit grids; mantissa
savings do not repay this grammar's tags and shared-exponent overhead.

The proposed extension retains original native repeat, absolute-gap and
temporal-delta Rice packets without extra bits. An impossible first absolute
gap, `M-9` for grid size `M=32/64`, enters the extension. Ten strictly ordered
indices require first gap ≤`M-10`, so valid native packets cannot collide with
that escape. Its Rice code costs 13/14 bits, in addition to the existing
changed/absolute prefix. The extension then has residual kind (spatial gaps or
temporal deltas), group plan (10/5/2/custom), three-bit widths and three-bit
shared exponents. Contiguous custom groups use four-bit lengths. The optimizer
counts every field and uses dynamic programming for custom boundaries.

The forced byte counts are predictions from this explicit cost model, not
claims that new files or an AVR decoder exist. Native reserialization must
match every actual byte, including final zero padding. Results and source hashes
are in [exact-analysis.json](../../experimental/LSF1/exact-analysis.json).
This rejects this grammar on these eight files; it is not a proof against every
possible LSF representation or corpus.

## Bounded lossy check

Exactly four deterministic proposals per file permit at most one LSF-bin error:
hold a close previous vector, snap individual close bins, round temporal deltas
to even values, or greedily choose among those and the incumbent. Reconstructed
vectors must remain ordered and in range. Everything else stays unchanged.

The 32 proposals are actually packed as original V9 and decoded by the current
native decoder, independently checked against model synthesis. Admission
requires a smaller actual file and no regression in PCM/PWM SSE, PCM/PWM STOI,
supported full-band spectral error/retention, level/spectrum guards, and every
interpolated filter's stability. These are deliberately strict engineering
criteria, not a blinded listening result.

**No proposal is admitted.** Some shrink a file, but fail quality checks; selected
files remain byte-identical to the original 8,587-byte set. See
[one-bin-gate.json](../../experimental/LSF1/one-bin-gate.json) for every proposal,
metric and rejection mask. No new decoder or full new-format AVR matrix is
justified after this gate.

## Current decoder CPU findings

Four full-file replays of existing source-verified ASM firmware profile
`chego-p4` and `bread-p6` on both ATtiny88 and ATmega328P. A host-only PC histogram
adds no firmware instructions. All original timing fields and complete PWM
remain identical, and flat instruction totals exactly equal the foreground
decode counters.

Bit readers account for 0.51–0.74% of Tiny decode CPU and 1.14–1.70% on Mega;
LSF conversion accounts for about 3–4%. Most work remains in the containing
inlined DSP/control function. These are flat instruction shares, not inclusive
call costs or a claim that the entire containing function is multiplication.
Changing only LSF packing therefore has little scope for a large CPU reduction.

A separate bounded eight-build screen preserves current LPX audio, decoder,
player and hardware. It tests Tiny multiply-unroll 4/8/16 and Mega function
tuning 7 on the same two complete files, against existing source/input-matched
baselines. Every pilot passes exact PWM, FIFO, IRQ, timing, EOF and observed
stack checks with zero underruns.

| Existing setting | Paired decode cycles/source sample | Program Flash change | Decision |
| --- | ---: | ---: | --- |
| Tiny unroll 4/8/16 versus 2 | 1,337.071 → 1,337.071 | 0 B | No benefit; linked Flash is identical |
| Mega tuning 7 versus 0 | 615.072 → 680.184 | +172 B | Reject; 10.59% more CPU |

Mega tuning also increases observed stack from 24 to 42 bytes. No setting is
selected and defaults remain unchanged. Tests use 16 MHz / 8 kHz, original
Timer0/Timer1 scheduling, FIFO32/prefill24, gain128 and active assembly ISR;
they are simavr 1.6 measurements, not physical-board tests. Portable C and
compiler-provided real device/memory macros remain untouched.

Full counters, build recipes, source/input/image hashes and limits are retained
in the [AVR report](../../experimental/LSF1/avr/README.md). The
[cookbook note](../../../../docs/avr-asm-cookbook/lsf-packing-gate.md) records
the reusable measurement and bounds lessons.

## Reproduce

Run from the repository root in the same Linux/WSL host/AVR toolchain as the
previous experiment. Input preparation needs standard-library Python only.

```sh
python3 Codecs/LPX/research/lsf1-2026-11-26/prepare_inputs.py
python3 Codecs/LPX/experimental/LSF1/analyze.py --output Codecs/LPX/experimental/LSF1/exact-analysis.json
python3 Codecs/LPX/experimental/LSF1/gate.py
python3 Codecs/LPX/experimental/LSF1/avr/tune_current.py --output build/lsf1-avr/tuning-pilot-v1 --jobs 2
```

`prepare_inputs.py --reuse PATH_TO_PRIOR_BUILD_LBG1_COMMON` avoids encoding
again, while retaining the hash/native checks and fresh quality measurements.
The profiler's README documents replay of existing case directories; a fresh
baseline can be produced with the original full-player runner. No downloads,
publication, production source edits or extra target memory are involved.

The separate [Z80 history review](z80-transfer.md) identifies an encoder-only
direction for future quality/size experiments. Its proposals are not measured
improvements from this study.
