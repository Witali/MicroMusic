# Wider lattice: spectrogram-led Vinni trial

The public Q4 stream and the first Q4-T1 experiment both leave speech formants
too diffuse and excess narrow harmonics too prominent. Global output tilt alone
does not reconstruct the moving formant ridges. This isolated experiment widens
the eight reflection-coefficient ranges from [-0.5, +0.4375] to [-0.875, +0.875]
and refits all speech bytes through the exact integer decoder. It retains the
same four-sample excitation; improvements cannot establish that this remaining
pulse model is adequate for natural speech.

## Public Vinni, complete 22272-sample phrase

All spectrogram comparisons use the same 70 Hz highpass, one global RMS match,
unchanged timing, and the shared `spectrogram-match-v1` target. Lower errors are
better. STOI/eSTOI are intelligibility proxies and do not measure naturalness.

| Measurement | Public Q4 | Rejected Q4-T1 | Q3-T1, spectral fitting |
|---|---:|---:|---:|
| Spectrogram loss | 0.629696 | 0.565548 | 0.504357 |
| Fine log error | 0.665630 | 0.547079 | 0.488444 |
| Mel-envelope error | 0.680469 | 0.671611 | 0.600814 |
| Unsupported energy | 0.284871 | 0.260780 | 0.200681 |
| Missing energy | 0.284073 | 0.243309 | 0.200337 |
| STOI | 0.859602 | 0.845375 | 0.838396 |
| eSTOI | 0.690986 | 0.667041 | 0.644611 |

The widened profile reduces the joint spectrogram error by 19.9% and unsupported
energy by 29.6% against public Q4. Its intelligibility proxies decrease. The
spectrogram still shows weaker formant contrast than the source. Keep this as
an audition candidate, not an accepted replacement or proof of naturalness.
The plain Q3 profile, without T1, ended at loss 0.574282 and STOI 0.833482 and
did not beat the combined profile.

The selected firmware is **1024 Flash bytes**, **zero EEPROM bytes**: 420-byte
core + 602-byte speech + EOF + one linker-alignment byte. All 66816 PCM samples
(22272 speech plus 44544 midpoint silence) match the independent oracle in the
reference, WASM, and unoptimized WASM engines. No overflow, dropped sample, or
lost timer event occurs. Worst preparation completes at 905 of 1280 cycles,
leaving 375 cycles. SRAM including stack spans 30 bytes. Hardware remains untested.

`public-vinni/` retains the final packed stream, final and initialization models,
search history, source/input fingerprints, independent spectral comparison, and
the actual AVR build/verification report. Generated WAVs, HEX files, and figures
stay in ignored build output. The source WAV is already retained as
`web-player/audio/originals/vinni.wav`.

Reproduce the bounded final 6000-proposal fitting phase from the retained seed:

```powershell
python tools/probe-hq4-q3.py --reference web-player/audio/originals/vinni.wav --stream ATtiny13A/Sound/codec/release/vinni/speech.hq --resume-model ATtiny13A/Sound/research/hq4-q3/public-vinni/seed-model.json --output build/hq4-q3/reproduce --proposals 6000 --tilt-shift 1 --spectrogram --build --avr-bin <avr-bin> --node <node>
```

The exact frozen final model can also be reassembled with the `build` function
in that tool, avoiding further optimization. Numerical decoding uses
`hq4_q3.render(frames, durations, 1)` and rejects any of its four wrap counts.

Possible follow-up: the first reflection coefficient can be near -0.95 in a
real speech spectrum. A separate first-stage coefficient map might extend the
negative range further, but needs its own integer-precision, code-size, cycle,
and quality study. This trial does not change that mapping or claim that it
would solve the remaining rough excitation.

## Tail voice under the composite decoder's 430-byte budget

The final “vhodit i vyhodit” excerpt keeps its preceding bell. Only the 12800
voice samples starting at sample 6528 are refitted here; bell level, frequencies,
and timing belong to the separate composite experiment.

The initial Q3 model comes from the latest 430-byte Q4-T1 voice: divide each
reflection coefficient by two, quantize to the nearest Q3 coefficient, then fit
6000 seeded joint proposals. Pitch, gain, frame boundaries, and coefficients
remain searchable. The final 430-byte stream has zero wraps and steps, peak 57.

| Measurement | Previous 430-byte Q4-T1 voice | Q3-T1 voice |
|---|---:|---:|
| Spectrogram loss | 0.617131 | 0.538359 |
| Fine log error | 0.648469 | 0.602608 |
| Mel-envelope error | 0.680350 | 0.548592 |
| Unsupported energy | 0.270521 | 0.186957 |
| Missing energy | 0.262232 | 0.189754 |
| STOI | 0.825079 | 0.836672 |
| eSTOI | 0.519951 | 0.550572 |

This candidate improves both intelligibility proxies and all four spectral
components over the previous voice at the same data budget. Its `training.json`
distinguishes that comparison from the older plain-Q4 voice used as input. The
full bell+voice image still needs its own actual AVR and timing report; the
430-byte data fit alone does not certify the composite firmware.

Reproduce after preparing the external source excerpt described in the retained
`natural-timbre/tail-voice-430/input.json`:

```powershell
python tools/probe-hq4-q3.py --reference build/new-speech/bell-hybrid/voice-reference.wav --stream ATtiny13A/Sound/research/natural-timbre/baseline-voice/speech.hq --resume-model ATtiny13A/Sound/research/hq4-q3/tail-voice/seed-model.json --output build/hq4-q3/tail-reproduce --proposals 6000 --tilt-shift 1 --spectrogram --stream-budget 430
```
