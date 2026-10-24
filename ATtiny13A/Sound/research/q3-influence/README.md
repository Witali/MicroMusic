# Equal-budget frequency/amplitude priority ablation

This is a bounded encoder experiment, not a human-perception weighting study.
All three profiles start from the same latest 430-byte Q3 tail-voice model,
receive 1500 proposals, and share the same precomputed per-step random schedule
(seed 23213). Only objective weights change; spectral weight and all eligibility
guards remain fixed. See `../../codec/HQ4_Q3_INFLUENCE.md` for the normalized
objective and complete method.

| Profile | Frequency weight | Amplitude weight | Evaluated physical proposals | Improved eligible elites |
|---|---:|---:|---:|---:|
| Frequency priority | 1 | 0 | 910 | 0 |
| Amplitude priority | 0 | 1 | 919 | 0 |
| Balanced | 0.5 | 0.5 | 910 | 0 |

All three selected streams, numerical PCM arrays, and audio hashes are identical
to the frozen baseline. Their normalized objective remains 1. The unchanged
measurements are mean frequency error 38.344 cents / 11.381 Hz, mean level error
5.381 dB, STOI 0.836699, eSTOI 0.551170, spectral loss 0.537795, 21.22% missing
tracked-reference energy, 31.80% extra tracked-candidate energy, and 78.78%
reference coverage.

This shows local search stagnation under the frozen memory, decoder, and quality
guards. It does not establish equal influence of frequency and intensity, or
that either factor is unimportant. The current run cannot quantify their
relative perceptual contribution. A controlled signal perturbation or a decoder
with independently controllable partials is needed to separate those effects.

`tail-voice/report.json` retains the baseline, per-profile complete metrics,
proposal schedule hash, accepted-step counts, source/input fingerprints, and
raw/matched audio hashes. Unchanged models are linked to their existing retained
source and qualified full AVR report instead of copied again. Generated audio
is in `build/hq4-q3-influence/tail-voice/`: original → baseline → frequency
priority → amplitude priority → balanced. The last four parts are identical.
The shared evaluation cache makes profile runtimes incomparable.

Reproduce:

```powershell
python tools/probe-hq4-q3-influence.py --reference build/new-speech/bell-hybrid/voice-reference.wav --model ATtiny13A/Sound/research/hq4-q3-tracks/tail-voice/model.json --output build/hq4-q3-influence/reproduce --proposals 1500 --stream-budget 430
```

The three guard/schedule tests pass. No new firmware is claimed: each selected
voice is byte-for-byte the previously qualified 1022-byte bell-plus-voice image's
voice, with its 64-byte EEPROM table unchanged.
