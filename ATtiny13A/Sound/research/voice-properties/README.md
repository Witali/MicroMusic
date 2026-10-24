# Comparing the good short voices with harder speech

This comparison uses the same automatic analysis on eight retained originals.
No character names, hand-selected vowels or per-recording thresholds enter
the estimator. Source and analysis hashes, complete estimated trajectories
and accepted persistent runs are in `reference-properties.json`.

## What actually differs

The public examples do not currently use one common decoder. In
`web-player/hq4-firmware.json`, Chego and Otvechaesh select `tiny-period`;
Vinni selects legacy `hq4`. Tiny synthesizes learned 32-point period shapes,
interpolates their phase positions, crossfades adjacent frames and adds an
independent high-band noise residual. HQ4 drives an eight-stage lattice with
either a fixed short pulse or binary noise, and restarts its pulse countdown
at frame changes. Thus the perceived difference confounds source voice,
decoder family, phrase duration and training history.

The good Tiny examples use 990 Flash + 64 EEPROM bytes each. The 2.970-second
Vinni HQ4 example uses 1024 Flash and no EEPROM; the good phrases are only
1.229 and 1.058 seconds. The failed Tiny Vinni reduction had to use four
period shapes instead of eight to fit the longer phrase. Simply transferring
the good decoder does not solve it: its STOI was 0.759 versus HQ4's 0.860.
See `../tiny-speech/vinni/README.md` and `../new-speech-naturalness/README.md`.

| Original | Estimated voiced F0 median, Hz | Active frames estimated periodic | Energy in active frames estimated nonperiodic |
| --- | ---: | ---: | ---: |
| Chego | 393 | 91.0% | 0.6% |
| Otvechaesh | 550 | 81.8% | 2.3% |
| Vinni, public full phrase | 133 | 53.1% | 33.6% |
| Final voice, bell excluded | 185 | 41.7% | 30.2% |
| ey-kto-nibud-dom | 348 | 88.1% | 4.3% |
| i-togo-i-drugogo | 289 | 68.3% | 15.1% |
| vinni-pu534 | 122 | 53.8% | 24.6% |
| vinni-pux-3543 | 198 | 56.9% | 15.9% |

These are estimates from our existing YIN-style tracker, not measured pitch
ground truth or semantic voice/noise labels. Aperiodicity, effects, harmonics
and subharmonics can confuse it. Vinni's persistent accepted run gives about
129 Hz; the first two persistent estimates are about 399 and 599 Hz. The
different raw and persistent estimates must not be substituted for exact
instantaneous excitation frequencies. The full public Vinni includes effects;
the final voice excludes its bell only for this additional diagnostic.

The results support investigating periodicity and excitation together. They
do not prove that low pitch alone causes bad synthesis. Lower pitch requires
more harmonics for the same spectral bandwidth, and irregular/noisy voice
cannot be represented accurately by a repeated clean period alone. With
32 samples per period, the base period table has only 16 independent harmonic
bins; interpolation and spectral images complicate any strict bandwidth
claim. A longer table is a hypothesis to test after excitation, not a proven
fix. The source-derived 10-partial measurements and full spectrogram remain
the quality controls.

## What is already ruled out or insufficient

- The independent HQ4 audit found no actual clipping or lattice overflows in
  these retained models. An overflow patch would not explain their defect.
- Continuous phase alone, pulse-width changes, and the learned Q3 cycle book
  did not preserve the required intelligibility; see the corresponding
  retained experiments. A closer local waveform is insufficient.
- Three independent sinusoidal tracks follow dominant peaks more closely,
  but lose too much speech detail and need 1034–1207 bytes of data for just
  the 1.707-second voice, excluding decoder and bell.
- Q3 coefficient-range expansion improved parts of the spectrum, but did not
  fix naturalness. Extending coefficient range again has no current evidence
  of necessity; the fitted coefficients rarely approach the available limit.

The concrete universal extension and regression policy are in
`../../codec/SPEECH_QUALITY_PLAN.md`. Existing good models stay frozen.

## Reproduction

`tools/compare-voice-properties.py` accepts repeated `--reference name=path`
and `--output report.json`. Supply the three canonical WAVs under
`web-player/audio/originals`, the exact 12800-sample final voice and the four
other prepared new MP3 references. Every source uses the same 7500 Hz rate.
No trimming or source-specific normalization occurs in this tool. Whole-file
band powers use a common 70 Hz highpass; F0 uses the existing tracker unchanged.
Original and generated audio are excluded from this directory.
