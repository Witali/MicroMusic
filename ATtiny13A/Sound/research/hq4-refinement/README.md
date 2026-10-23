# Guarded HQ4 refinement, 2026-10-23

The accepted original HQ4 is the starting point. This experiment changes only
its compressed stream; the real one-shot decoder remains 406 bytes. It is
separate from the rejected voice-priority period-wave prototype and does not
replace the selected public tiny examples or the accepted public Vinni HQ4.

All parameters are chosen automatically. Seed 23101, 6,000 proposals for each
short recording and 12,000 for Vinni. The fixed objective weights are 70%
multi-resolution STFT loss, 20% band envelope/shape loss and 10% persistent-ridge
spectral loss. Both STOI and eSTOI and the original spectral ceilings are hard
export guards against the frozen HQ4. See [the algorithm](../../codec/HQ4_REFINEMENT.md).

| Recording | STOI before → after | eSTOI before → after | Log-spectrum error before → after | Flash / EEPROM |
| --- | ---: | ---: | ---: | ---: |
| Chego | 0.9006005 → 0.9006086 | 0.7954517 → 0.7969757 | 1.2769259 → 1.2261458 | 958 / 0 |
| Otvechaesh | 0.8190556 → 0.8190654 | 0.7041273 → 0.7042365 | 1.1921569 → 1.1799393 | 916 / 0 |
| Vinni | 0.8596023 → 0.8596223 | 0.6909859 → 0.6933715 | 0.8128841 → 0.7951900 | 1024 / 0 |

The relative log-error reductions are 3.98%, 1.02% and 2.18%. These are changes
in a specific engineering metric, not percentages of audible improvement.
The small intelligibility differences do not establish subjective superiority.
For Chego and Otvechaesh the current public tiny models remain substantially
better than these original-HQ4 refinements under the saved quality measures.
Vinni needs matched listening before a public replacement is considered.

The search really changes the temporal allocation: frame counts 93 → 92,
83 → 88 and 140 → 138. Total lengths stay exactly 9,216 / 7,936 / 22,272 samples.
Band loss improves 0.903655 → 0.893512, 0.847411 → 0.844196 and
0.728559 → 0.725206. Individual loss components can trade off; all final metrics
and every accepted elite are retained in each `training.json`.

Each directory contains the canonical compressed source `speech.hq`, search
provenance `training.json` and the independently assembled `build.json`.
SHA-256 of the stream and first-phrase PCM agrees between search and actual
AVR qualification. All three engines (JS reference, WASM, unoptimized WASM)
match the whole phrase followed by twice its length of constant midpoint 128.
Verified samples: 27,648 / 23,808 / 66,816. No missed samples or timer overflows;
minimum full-preparation slack 294 / 285 / 216 CPU cycles. Erased EEPROM in the
verifier is test scaffolding; these HQ4 images use zero EEPROM bytes.
Hardware has not been tested.

```powershell
python tools/refine-hq4-speech.py --clip vinni --reference C:/Work/MicroMusic/build/hq4-preview/vinni/original.wav --output build/hq4-refinement/final/vinni --proposals 12000 --seed 23101 --checkpoint-every 1500
python tools/build-hq4-oneshot.py --clip vinni --stream ATtiny13A/Sound/research/hq4-refinement/vinni/speech.hq --output build/hq4-refinement/rebuild/vinni --avr-bin C:/Work/MicroMusic/build/toolchains/avr-7.3.0/bin --node C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe
```

For the short recordings use the corresponding clip and original with 6,000
proposals. Keep NumPy/SciPy/Numba/pystoi versions from the retained reports,
`OPENBLAS_NUM_THREADS=1`, and source hashes unchanged for exact reproduction.

Listening assets stay in ignored `build/hq4-refinement/final/<clip>/`:
`original-matched.wav`, `before-matched.wav`, `after-matched.wav`, `comparison.wav`.
The comparison is original → HQ4 → original → refined HQ4, with identical
highpass/RMS/peak treatment and 300 ms gaps. `decoded.wav` retains the exact
unfiltered synthesized PCM level.

The [frequency analysis](../speech-spectrum/README.md) retains time spans and
deficits/excesses; it does not prescribe static sinusoidal overlays or notches.
A [separate mixed-excitation probe](../hq4-mixed/README.md) was rejected because
its best spectral improvement weakened intelligibility. Joint excitation/filter
search and a more efficient residual remain possible next experiments, with
decoder code and EEPROM cost included explicitly.
