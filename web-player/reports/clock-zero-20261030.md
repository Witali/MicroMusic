# Zero-ratio shortcut: not retained

The pure clock helper candidate returned quotient zero/remainder carry for a
zero multiplicand with proper carry, after the original zero-divisor guard.
It preserved event servicing and all clock/retirement boundaries. See the
[arithmetic proof and reconstruction](../../docs/avr-asm-cookbook/zero-clock-ratio.md).
**Production arithmetic and native artifacts are restored exactly to `702450d8`.**

Baseline native: 124614 bytes, SHA-256
`b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`.
Candidate: 124631 bytes, SHA-256
`eea8e51960022da56d211519da8e1b61e87d386040343f8d9fdbd6e462f1957e`.
Only `ratio` (index 155) differs among 218 function bodies: 522 to 539 bytes.
Compiler flags, source list, exports, no-import contract and fixed memory agree.

## Correctness and performance decision

Before editing, the selected clock/deadline set passed 22/22. The candidate
passed all seven clock tests, including 225 new zero/carry/divisor combinations
and unchanged failure outputs. All 16 equal-policy workload comparisons passed,
covering compatible/physical music, direct execution, CLKI /1 and /256, and
active ADC/watchdog controls with identical generated CPU bytes/ABI.
Recorded PCM, full architectural/diagnostic snapshots and tail pins matched.
This is scoped software parity, not full waveform or hardware acquisition.

The initial screen uses 12000 music frames, 1200 CLKI frames at 48 kHz and one
million direct instructions. Each case has eight balanced four-label trials
and four full-workload warmups per label. Ratios below are old/new elapsed time;
values above one favor the candidate. Old/old and new/new are null controls.

| Initial case | Old/old median | New/new median | Old/new median | Candidate faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Rhythmic physical | 0.997 | 0.985 | 0.992 | 3/8 |
| Lumière stereo physical | 1.013 | 1.018 | 1.017 | 5/8 |
| Physical direct kernel | 1.001 | 1.018 | 1.061 | 7/8 |
| CLKI 20 MHz /1 | 0.999 | 1.029 | 0.989 | 2/8 |

Null controls vary materially; the apparent direct gain does not establish a
general improvement. The longer confirmation increased music to 48000 frames,
direct work to ten million instructions and CLKI to 4800 frames. Only its first
completed workload is retained: Rhythmic old/old 1.005, new/new 1.038,
old/new **0.957**, candidate faster in **2/8** pairs. The reciprocal of this
reported median is about 1.0446, with substantial null variation. It does not
prove a stable regression, but does not establish a useful speedup.

The remaining confirmation was intentionally interrupted after this result.
Its summary remains `complete:false`; unpublished partial work is excluded.
Totals cover **160 completed timed runs, 80 warmups and 3567 exact checkpoints**,
including the 16-workload parity set. Tests/profilers/other benchmarks were not
run alongside timing. Host load, frequency, GC and V8 tiering remain uncontrolled.

After restoration, **23/23** focused clock/deadline checks pass. The new generic
225-case test and named experimental harness mode remain useful for future
verification; the shortcut is absent. No full candidate runtime suite was run
after the performance gate failed. The earlier 2659 full checks belong to the
exact unchanged production runtime; this experiment creates no hardware or
real-time admission claim. Native/site artifacts and compiler identity remain
at the preceding production checkpoint.

## Retained evidence

[JSON evidence](clock-zero-20261030.json) retains every completed individual
duration and ratio, workload/options, output hashes, candidate insertion,
source/input/TAP hashes and explicit incomplete-confirmation status. Original
captures, candidate header/WASM/manifest and TAP files remain under ignored
`build/clock-zero-20261030/`. The collector verifies raw output equality,
recomputes ratios, checks the exact candidate body change and requires current
production restoration before emitting the report:

```text
node web-player/scripts/verify-clock-zero.mjs --output build/clock-zero-evidence-replay.json
```

The initial new-test launch had an incorrect expected combination count (210);
all arithmetic comparisons passed. The count was corrected to 225 before the
retained passing clock TAP. No model assertion was weakened. No download or
installation occurred. Seven plan items remain open; **24/31** are complete.
