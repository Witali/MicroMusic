# P3 intelligibility investigation

The user confirmed that both the original-rate and prepared 8-kHz source of
development example 3 are intelligible, while both its current P3 and previously
selected fine-grid output are unintelligible. These are informal observations,
not a blind listening score. Original media, fingerprints, arrays and models
remain ignored. The earlier study is preserved in its original worktree.

## Diagnosis

Independent implementations reproduced every one of the 160,000 saved samples.
Actual bit fields, Long lengths, signs, de-emphasis and temporal alignment
matched. No arithmetic or packing defect was demonstrated.

With identical source LPC analysis and pre-emphasis, the spectral ablation was:

| Representation | LPC prediction gain | Source-onset envelope error RMS |
| --- | ---: | ---: |
| Fresh P4 grid, no hold | 4.872 dB | 2.825 dB |
| P3 rank grid, no hold | 3.294 dB | 3.902 dB |
| P3 rank grid plus legacy dead zone | .592 dB | 5.073 dB |

All 8,000 interpolated filters in each ablation were stable. The saved P3
spectra updated in 119/500 frames and remained fixed for up to 680 ms. This
supports removing the additional hold as a narrow candidate correction.

Excitation is also a major limitation: keeping the encoded coefficients,
scales and postfilter but allowing six-bit innovation at every sample gives
29.09 dB SER instead of 5.99 dB. That dense control has a radically higher
information rate and is not an LPX file or a viable compressed fix.

## Candidate and bounded checks

`LpxSpectrumQuantizer.h` retains the even rank-residual grid but defaults the
extra temporal dead zone to zero. An explicit value of 2 selects the old
policy. Wire syntax and decoder code are unchanged. Other accuracy levels
bypass this quantizer as before.

On the complete 20-second example, with the same ordinary four-call pipeline:

| Output | Bytes | PCM STOI | PCM SSE |
| --- | ---: | ---: | ---: |
| Previous current P3 | 7,236 | .735744 | 50,625,173,643 |
| Previous selected fine-grid proposal | 7,195 | .776484 | 36,657,203,515 |
| New immediate-update P3 candidate | 8,207 | .787465 | 44,564,938,439 |

The candidate updates 489/500 spectral frames, has no PCM clipping and matches
the complete native decoder output. Its WAV readback is byte-exact. It grows
the file by 13.42% against the current P3 and does not improve every metric
against the earlier selected proposal. On 2026-11-26 the user subsequently
reported this exact candidate **clearer than the preceding examples**. This
informal rating covers one known development example; complete intelligibility
and generalization remain unestablished. `results.json` preserves its original
pre-listening status. The user subsequently requested integration into `main`.

Synthetic tests pass for default 0 and legacy 2: small spectral changes,
10,000 ordered vectors per configuration, idempotence and unchanged non-P3
levels. A fresh legacy-2 native build reproduces the original fast-control
LPX and PCM bytes exactly. Scalar GCC 13.3 uses `-O3 -std=c++11
-ffp-contract=off` and the project's portable decoder defines. The normal
four-call result equals the new fast result on this example; its 55.28-second
time is a single host measurement, not an AVR deadline result.

Run the synthetic regression with:

```powershell
$env:LPX_TEST_WSL='Ubuntu'
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/test_p3_temporal.py
```

[Anonymous results](results.json) also retain P4/P6/P8 and no-pre-emphasis
controls. P6 and P8 fast controls are identical here. `controls.cpp` is the
native diagnostic entry point: link it with the shared host/core sources and
portable defines listed in `web-player/scripts/lib/lpx-build.mjs`; input is
PCM16 little-endian and arguments are reference path, output prefix and mode
(`3`, `4`, `6`, `8`, `4-nopre` or `3-full`). Each process reserves its own
encoder workspace. Generated LPX, PCM, models and listening WAVs stay ignored.

The user requested a faster conclusion, so this stage stops after one
source-confirmed development failure, mechanistic checks and this candidate.
No new corpus sweep, unseen-quality claim, old held-out tuning, WASM execution
or AVR timing measurement was performed. More frequent spectral updates can
increase existing decoder work even though decoder source is unchanged.

For the subsequent authorized merge/publication, scalar and SIMD WebAssembly
assets were rebuilt with the existing Emscripten 6.0.12 toolchain. Both actual
browser backends reproduce the native candidate's 8,207 LPX bytes and all
160,000 PCM samples exactly on this same development excerpt. Twenty-one
quality-target, bitrate, worker and stream-limit tests pass against the rebuilt
assets. This adds execution/packaging evidence, not a new independent listening
or corpus-quality result. AVR interrupt timing remains unmeasured.
