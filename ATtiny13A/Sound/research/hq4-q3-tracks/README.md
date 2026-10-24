# Bounded fitting of the ten strongest original partials

These experiments continue from the frozen Q3 models, leaving the earlier
models and decoder sources unchanged. The new optional fitter searches all
frame parameters automatically against original/output spectral and harmonic
trajectory differences. See `../../codec/HQ4_Q3_TRACKS.md` for the exact target
and eligibility guards.

The track analysis uses the ten strongest local peaks at each time, a 1024-point
Hann STFT, a 128-sample hop, and interpolated peak frequency/amplitude. Reference
tracks are cached. Matching uses unchanged time and a physical gate of 100 cents
with a two-bin Hz floor. Its loss tolerances are 50 cents and 3 dB; these are
normalization settings, not a claim that the actual errors meet those limits.

Both trials make 4000 seeded proposals. STOI/eSTOI, all four spectral components,
missing/extra tracked energy, continuity-break rate, and weighted coverage are
guarded against the corresponding frozen Q3 baseline. Infeasible working states
can be explored, while only feasible elites are retained.

## Public Vinni: no qualified improvement

The public Vinni Q3 candidate remains **byte-for-byte unchanged** after this
bounded run. There are 2415 physically valid evaluated proposals and no improved
feasible elite. The retained report links the original Q3 model and qualified
AVR report rather than duplicating an unchanged stream.

Its matched partials still have mean errors of 48.64 cents / 11.04 Hz and 7.38 dB,
17.28% unmatched reference energy, 23.62% extra candidate energy, and 82.72%
matched-reference coverage. Small matched-frequency error alone is insufficient:
partial levels, missing energy, and continuity remain substantial limitations.
This negative result is not presented as a new playback improvement.

## Final tail voice: small qualified improvement

| Voice measurement | Previous Q3 | Track-fitted Q3 |
|---|---:|---:|
| Harmonic-track loss | 0.761314 | 0.748523 |
| Spectrogram loss | 0.538359 | 0.537795 |
| Mean frequency error, cents | 39.1596 | 38.3441 |
| Mean frequency error, Hz | 11.6171 | 11.3807 |
| p95 frequency error, Hz | 30.8667 | 26.4976 |
| Mean amplitude error, dB | 5.47302 | 5.38117 |
| p95 amplitude error, dB | 13.88028 | 13.88274 |
| Missing reference energy | 0.213417 | 0.212227 |
| Extra candidate energy | 0.319394 | 0.317959 |
| Matched-reference coverage | 0.786583 | 0.787773 |
| Continuity-break rate | 0.341341 | 0.331331 |
| STOI | 0.836672 | 0.836699 |
| eSTOI | 0.550572 | 0.551170 |

The harmonic loss improves by 1.68% and spectrogram loss by 0.10%. All frozen
eligibility guards hold. The p95 amplitude error is slightly worse and is shown
explicitly; it is not one of this run's hard guards. These are modest numerical
gains and do not demonstrate an audible solution to the remaining rough voice.

The voice still occupies 430 stream bytes. The complete automatically balanced
bell-plus-voice image is actually assembled and verified: **1022 Flash bytes,
64 EEPROM bytes**, 576-byte core, 15-byte bell descriptor, 430 voice bytes and
EOF. All **57984 PCM samples** (19328 phrase plus 38656 midpoint silence) agree
across the three emulator engines. There are no mismatches, lost overflows, or
missed samples; the minimum preparation slack is 419 cycles. Hardware and human
listening remain unverified.

Retained directories contain only source models, the compressed speech data, and
linked training/build/quality reports. Generated WAV, HEX, EEPROM binaries and
track figures remain under ignored `build/hq4-q3-tracks/`. The native full AVR
comparison there is original → previous Q4-T1 hybrid → track-fitted Q3 hybrid.

Reproduce fitting:

```powershell
python tools/probe-hq4-q3-tracks.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --output build/hq4-q3-tracks/public-reproduce --proposals 4000 --harmonic-tracks 10
python tools/probe-hq4-q3-tracks.py --reference build/new-speech/bell-hybrid/voice-reference.wav --model ATtiny13A/Sound/research/hq4-q3/tail-voice/model.json --output build/hq4-q3-tracks/tail-reproduce --proposals 4000 --harmonic-tracks 10 --stream-budget 430
```

The external tail-reference preparation and provenance remain linked from
`../natural-timbre/tail-voice-430/input.json`. Rebuild the retained final image:

```powershell
python tools/build-q3-bell-hq4.py --reference build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav --bell-model ATtiny13A/Sound/research/new-speech-naturalness/bell-hybrid-t1/balanced/model.json --voice-model ATtiny13A/Sound/research/hq4-q3-tracks/tail-voice/model.json --output build/hq4-q3-tracks/bell-reproduce --avr-bin <avr-bin> --node <node>
```
