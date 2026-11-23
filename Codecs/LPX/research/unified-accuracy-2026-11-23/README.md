# Unified precision policy: paired checks

This is a small development/regression check of the frozen direct accuracy
policy in [ACCURACY.md](../../01_ACTIVE_Q0_CODEC/host/ACCURACY.md), not a fresh
heldout listening study. P6 and P8 use identical prepared PCM, sample rate,
calls=4 and preserve-level input. P8 is encoded directly. There is no production
P6 companion encode, source gain fitting, delay fitting or new wire syntax.

The three retained public speech WAVs are resampled from their actual 7500 Hz
to 8000 Hz with the shared C++ FIR. Complete scalar/SIMD LPX bytes agree for
both presets, and the common C decoder verifies every final sample and EOF.
Independent native evaluation uses the frozen 18 speech/PCM/PWM fields and 90
native-band/time fields, without changing equations or weights.

| Public source | P6 bytes | P8 bytes | Relative joint-error change |
| --- | ---: | ---: | ---: |
| chego | 773 | 982 | -29.4855% |
| otvechaesh | 668 | 668 | 0; exact tie |
| vinni | 2227 | 2361 | -2.9588% |

Two streams changed and one tied. These are source-dependent objective gains,
not proof of audible superiority. All individual speech and native-band/time
tradeoffs are retained in [public-paired.json](public-paired.json), including
increases in individual losses; the joint score must not hide them. The score
uses one frozen paired P6 denominator, including exact-zero floors, for this
offline comparison only. It is never multiplied by a previous stage's score.

Specifically, vinni's PCM STOI falls by 0.001078, its PCM noise loss rises by
0.8277%, and the largest native-band error/time increases are 4.4429%/7.0407%.
Its aggregate spectral/time errors still fall on both PCM/PWM paths. chego's
PCM pitch-shape loss rises by 1.6836%. These tradeoffs rule out a claim that
every metric or band improved. The production guard protects each preset's
own original seed, not an independently completed different preset.

The separate fixed known-wideband check selected the first three distinct
already-used development sources at prepared 16 kHz, before this policy's
outputs were read. Original source rates are 16/48 kHz. All three P6/P8 pairs
tie exactly: total 24715 bytes for each preset, every metric/band/time delta
zero. This demonstrates no extra P8 benefit on those controls. The
[anonymous aggregate](wideband-aggregate.json) excludes identities, bindings,
media, individual rows and local paths. No parameters were refitted from it.

Public listening pairs remain local generated WAV/LPX artifacts. Listening
has not established an audible gain. The actual allocations allow more P8
detail, but do not guarantee that every recording or high-frequency band
benefits. Broader independent and listening validation is still useful.

## Reproduction and limits

Build with the retained `web-player/scripts/build-lpx-wasm.mjs` and
`build-lpx-native.mjs` helpers; manifests bind every production source and binary.
Use the unchanged `tests/helpers/lpx-quality-native.cpp` evaluator for both
whole paired outputs at their actual rate. The allocation and exact complete
V9 cap are checked by the production common selector, while legacy strict-cap
APIs and their regression matrix remain separate.

Tests cover all four presets at 8/12/16 kHz, native/scalar/SIMD equality,
malformed requests/reuse, original legacy API behavior, continuous window
boundaries, normalization and final decoded samples. The streaming P8 test
asserts exactly one production session, preventing accidental companion P6
encoding from returning. Input transport has separate format/memory tests.

The [archived FAST activation pair](anonymous-fast-pair.md) and its
[anonymous numeric receipt](anonymous-fast-pair.json) measure a previous,
immutable calls=0 correction proposal on six interrupt-active simavr images.
They are useful decoder parameter-activation evidence, not final-policy,
physical-board, higher-rate or arbitrary-stream support. Tiny P8 exceeds the
6012-byte bootloader application region in that example; do not infer fit from
the unchanged decoder source.
