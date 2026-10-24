# HQ4-T natural-timbre listening experiments

These are private listening alternatives, not replacements for the public
selected firmware. A smoother spectrum does not prove a more natural voice.
The original HQ4 samples remain the controls, and no hardware listening test or
subjective naturalness win is claimed.

The compact T1 decoder occupies 418 bytes, with no EEPROM. It adds
`y = s8(x + previous - (previous >> 1))` after the unchanged integer lattice.
Automatic parameter search includes pitch, gain, excitation, coefficient halves
and frame boundaries. Every sample is retained. Internal lattice/output wraps
cannot increase, and every exported candidate has zero such wraps and no
adjacent PWM step of at least 48 units.

| Candidate | Before STOI → T1 | Before eSTOI → T1 | Log spectrum before → T1 | Actual Flash |
|---|---:|---:|---:|---:|
| Public Vinni, full phrase | .85960 → .84538 | .69099 → .66704 | .81288 → .67857 | 1022 |
| Final recording, voice only | .78859 → .85188 | .44984 → .55309 | .85529 → .79178 | 994 |
| Same voice, 430-byte stream cap | .78859 → .82508 | .44984 → .51995 | .85529 → .80218 | 850 |

The Vinni result trades some measured intelligibility for a substantially softer
spectral envelope, so it is retained as an audition candidate only. The voice
results improve both intelligibility proxies and spectrum against their 410-byte
voice-only control. The capped result leaves room for the independently tested
bell prelude; its standalone size is not the composite image size.

All three actual HEX images were independently checked with reference, WASM and
unoptimized WASM AVR engines: one full phrase followed by twice its duration of
midpoint silence, no mismatched samples, lost Timer0 events or missed samples.
Minimum measured timing slack was 207/294/330 CPU cycles respectively at 9.6 MHz.
The erased 64-byte EEPROM in verifier fixtures is not used by these firmwares.

Per-candidate directories retain compressed frame models, canonical streams,
training summaries and complete AVR qualification reports. Original/reconstructed
WAV, HEX, binaries and optimizer trajectories stay in ignored `build/`. Listening
files at `build/new-speech/natural-timbre/<candidate>/comparison.wav` use the order
original → ordinary HQ4 → original → T1, with identical 70-Hz highpass, RMS
matching and a common final peak scale. The verified raw AVR recording equals
the exact numerical candidate before this common listening-only processing.

Brightness diagnostics include Welch centroid/high-frequency power, distinct
PWM values and sample-difference RMS. They are physical descriptors, not a
naturalness score. Reported PWM RMS includes DC; mean PWM is reported separately.
The T filter amplifies DC bias as well as low frequencies, so raw RMS-difference
ratios should not be interpreted as a perceptual roughness improvement alone.

## Reproduce

Public Vinni's exact reference is already retained as
`web-player/audio/originals/vinni.wav`; source stream is
`ATtiny13A/Sound/codec/release/vinni/speech.hq`.

```sh
python tools/probe-hq4-natural-timbre.py \
  --reference web-player/audio/originals/vinni.wav \
  --stream ATtiny13A/Sound/codec/release/vinni/speech.hq \
  --output build/new-speech/natural-timbre/public-vinni \
  --tilt-shift 1 --stream-budget 603 --proposals 4000 --seed 23130 --build
```

Add `--avr-bin <directory>` and `--node <executable>` when the AVR tools and Node
are not on PATH. Profile-specific source and decoder callback hashes supplement
the standard build report's source hashes.

The voice reference is the final input selection of `vhodit-i-vyhodit.mp3`
(14.24..16.812 seconds), prepared under its retained input report, then sliced
at sample 6528 of the prepared 19328-sample WAV. Its final 12800 samples are
retained in full. The baseline compressed voice model/stream are included in
`baseline-voice/` so the 410-byte control can be recreated without a generated
firmware image. Its prepared-reference SHA is recorded in the model.

Run the same tool using that prepared voice reference and `baseline-voice/speech.hq`:
use `--tilt-shift 1 --stream-budget 603 --proposals 4000 --seed 23131` for the
full standalone trial, or `--tilt-shift 1 --stream-budget 430 --proposals 5000
--seed 23132` for the capped composite-input trial. Do not substitute MP3 decoder
output from another preprocessing pipeline without checking the WAV SHA.
