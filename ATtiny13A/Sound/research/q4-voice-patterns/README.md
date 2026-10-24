# Voice patterns and selective Q4 precision

PC feasibility study, 2026-10-24. The user's proposal is to learn voice patterns
that preserve important frequencies. Here a pattern represents an LPC spectral
envelope and excitation selector. Pitch, half-sample period, gain and duration
remain per-frame controls. Several patterns are needed as the speech changes.
Reflection coefficients determine resonances indirectly; their numerical values
are not frequencies in Hz. These experiments do not add independent sine waves.

The existing [qualified half-pitch firmware](../q3-adaptive/README.md) remains
selected: **1022 Flash + 64 EEPROM**, STOI **0.853087**. None of the new pattern
candidates replaces it. New table/stream sizes below exclude the AVR decoder,
EOF and waveform storage. There is no new assembly implementation or Flash-fit
claim, and the good public examples have not changed.

## What was measured

All variants use the complete, unchanged mono 7500 Hz Vinni original: 22,272
samples. Each proposal is rendered through the integer lattice, including
signed-byte negation, half-period alternation, frame transitions and output
tilt. Even Q4 coefficients reproduce the previous Q3 PCM and all four arithmetic
counters exactly. This is checked against both the source-derived old renderer
and its frozen PCM hash.

| Variant | Logical data bytes | STOI | eSTOI | Spectral loss |
| --- | ---: | ---: | ---: | ---: |
| Selected Q3, half pitch | 647 | 0.853087 | 0.669892 | 0.484848 |
| Per-frame Q4 diagnostic | Not serialized | 0.857338 | 0.677784 | 0.481816 |
| 16 complete Q4 patterns | 425 | Guard failure | — | — |
| 32 complete Q4 patterns, fitted | 568 | 0.758492 | 0.509386 | 0.527493 |
| 16 shared tails + two Q4 controls, fitted | 526 | 0.810612 | 0.586036 | 0.502698 |

The diagnostic is **one bounded coordinate pass**, not a quality ceiling. It
keeps a separate eight-coefficient Q4 vector for every frame, without attempting
to fit 1 KB. Its smaller coefficient step improves the measured objective only
slightly: strong-component frequency error 51.4215 → 48.7091 cents and level
error 6.8383 → 6.5709 dB. Raw DC worsens +0.077640 → +0.079846. It is not a
qualified firmware improvement.

## Formats and fitting

[`q4_voice_patterns.py`](../../codec/q4_voice_patterns.py) defines the exact PC
layouts and renderer. A complete pattern stores eight Q4 coefficients in eight
bytes. The three-bit waveform selector shares the biased first coefficient's
byte. Frames store pitch/duration, gain and a five-bit pattern index. Indices
16–31 force an extended header. Reordering places frequent cheap indices first.

The first study performs 2112 per-frame Q4 coordinate trials, initializes 16/32
patterns using weighted spectral medoids, then attempts 1600 shared-coefficient
trials per valid dictionary. The spectral clustering is only an initializer:
full-clip STOI and spectrum select actual changes. The 16-pattern initializer
has peak 124, above the 115-count guard, so its refinement is skipped; no
arithmetic wraps occur. The 32-pattern
fit improves its initial STOI 0.721840 → 0.758492, still substantially below the
selected firmware. Full results and models: [`full/report.json`](full/report.json).

The second study tests selective precision. Every frame keeps K1/K2 independently
at Q4 precision; six even Q4 coefficients, equivalent to Q3, and the excitation
selector come from one of 16 shared tails. Each four-byte tail contains three
packed coefficient bytes plus one selector byte. The two extra precision bits
per frame form a separate plane, four frames per byte:

- Tail table: **64 bytes**.
- Precision plane: **33 bytes**.
- Frame stream, including each frame's two Q3 quotients: **429 bytes**.
- Total: **526 bytes**, 121 fewer logical bytes than the selected model.

This fit tries every tail for each frame, then per-frame head coefficients,
1500 tail-coordinate proposals and gains: 4270 exact evaluations in total.
STOI rises 0.728357 → 0.810612. Final arithmetic counts are all zero, peak 115,
maximum step 37. The serialized sections are read back and compared field by
field. The remaining quality loss rejects it as a replacement.

Its matched-component level error improves to 6.0121 dB, but frequency error
worsens to 52.8856 cents, missing-reference energy rises and STOI/eSTOI fall.
This confirms that one attractive harmonic metric cannot establish overall
quality. Raw DC also worsens to +0.086281. Results:
[`selective/report.json`](selective/report.json).

The exploratory selection energy is `spectrogram_loss + 6*max(0, .9-STOI)`;
arithmetic wraps, peaks above 115 and steps of 48 or more reject proposals.
These guards are weaker than the selected firmware's complete acceptance rules:
DC and harmonic metrics are measured at the end, not constrained during these
fits. Neither result is accepted under the final quality gates.

## Next format experiment

The useful direction is **spectral pattern + sparse corrections**. A small
dictionary must not force all eight coefficients to change together. Keep
pitch/gain separate, allow corrections for whichever resonances need them, and
use direct values for difficult transitions when their cost is justified.
Quantization precision and the number of corrections should be selected by
the original-vs-integer-output error and total size, rather than being fixed
for every frame. Test joint/factorized residuals as well as two independent
head controls; the latter alone did not recover the lost intelligibility.

[Opus RFC 6716, section 5.2.3.5](https://www.rfc-editor.org/rfc/rfc6716.html#section-5.2.3.5)
provides a relevant primary-source example: a spectral vector codebook followed
by coding of its residual error. Opus uses LSFs and much larger machinery. This
is an algorithmic reference, not a claim that its implementation fits ATtiny13A.
Any frequency/LSF analysis can remain on the PC; the tiny decoder should receive
precomputed stable coefficients and cheap updates.

Require no regression in STOI, eSTOI, spectrum, tracked components or DC before
porting a candidate. Then measure the complete Flash/EEPROM/SRAM/cycle budget,
compare actual assembled PCM in all three engines, and test protected RU/EN
examples. The absolute 0.90 / 0.344976 targets remain unmet.

## Reproduction

Code revision and hashes are in [`manifest.json`](manifest.json). With the
project's NumPy/Numba/SoundFile/speech-metric dependencies, run from the root:

```powershell
python tools/probe-q4-voice-patterns.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json --output build/q4-voice-patterns/full --patterns 16 32 --polish 1600 --ceiling 2112
python tools/probe-q4-selective-patterns.py --reference web-player/audio/originals/vinni.wav --control build/q4-voice-patterns/full/per-frame-control.json --output build/q4-voice-patterns/selective --trials 1500
python tools/test-q4-voice-patterns.py
```

Models, reports and scripts are retained; compiled intermediates stay in
ignored `build/`. `--ceiling` names the diagnostic trial budget, not a proven
upper bound on possible quality. The per-frame control has its own explicitly
unserialized schema and is not a legal 132-entry complete-pattern table.

Six targeted tests pass: five cover fixed-point arithmetic and packet contracts;
one reproduces retained candidates' PCM hashes, data sizes, STOI, eSTOI and
spectral error. The previous 381-test run and subsequent phase-specific AVR
checks remain separate evidence for the unchanged selected half-pitch firmware.
