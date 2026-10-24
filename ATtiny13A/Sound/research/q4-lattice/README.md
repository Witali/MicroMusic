# Fractional lattice states and a quality teacher

The active goal is **STOI ≥0.93**, with the unchanged complete Vinni source,
1024 bytes for decoder plus speech, 64 EEPROM, and the existing spectral target
≤0.3449755536. This study makes progress on the PC reference; it does **not**
meet those goals or replace the qualified 1022-byte half-pitch firmware.

## Measured first fitting cycle

| Complete 22,272-sample Vinni | STOI | eSTOI | Spectral loss | Raw DC |
| --- | ---: | ---: | ---: | ---: |
| Qualified half-pitch firmware | 0.853087 | 0.669892 | 0.484848 | +0.077640 |
| Unserialized Q4 coefficient control | 0.857338 | 0.677784 | 0.481816 | +0.079846 |
| Byte states, fine excitation, 12,000 trials | 0.861327 | 0.685303 | 0.478664 | +0.080203 |
| Word states with four fractional bits, 12,000 trials | **0.871019** | **0.708960** | **0.470751** | **+0.020399** |

The word result improves STOI by 0.01793 and eSTOI by 0.03907 relative to the
qualified firmware, reduces spectral error by **2.91%**, and reduces raw DC by
**73.73%**. Arithmetic counts are zero; the signed peak is 87 and maximum step
45. This is exact integer PC output. No new AVR decoder, timing proof, complete
image or physical-hardware result exists.

The byte result has worse raw DC and is not accepted as a replacement. Its
`best_intelligibility` record remains the initial Q4 control: the warm start is
recorded even though it exceeds the later DC ceiling. That name is not proof
of passing all export gates. The word result's balanced and best-intelligibility
endpoints are identical; only one copy of its source model is retained.

## What changed

The source-defined pulse timing, half-period alternation, LFSR, transitions and
last-frame convention stay available as an exact control. The byte profile
reproduces the qualified complete PCM hash. Reflection coefficients use Q4.
The new filter can keep sixteen-bit states with fractional samples instead of
rounding every intermediate to an eight-bit sample.

Wave taps and gains also have half-unit precision. Their product has two
fractional bits, which the word filter preserves. A doubled old tap and doubled
old gain reproduce the old excitation after division by four. Noise has no
wave tap, so its doubled gain requires division by two. A frozen-PCM test caught
and corrected that distinction before the retained searches. The two incorrect
initial searches were stopped and their outputs are not retained here.

`tools/refine-q4-lattice.py` automatically fits coefficients, gains, integer and
half periods, waveform selectors, all sixteen taps, adjacent frame boundaries
and splits into unused waveform slots. The two retained runs each evaluate
12,000 proposals from the same Q4 control. Proposals use complete integer output,
the unchanged STOI/spectrum objective with target 0.93, and hard wrap/peak/step
guards. Detailed secondary metrics are evaluated at endpoints; this search
does not enforce every qualified-firmware harmonic/DC gate on every move.

The word result's mean matched-component level error falls **6.8383 → 5.9339 dB**,
but frequency error slightly worsens **51.4215 → 51.7760 cents**. Its p95 level
error remains 13.7472 dB. The all-components 5 dB requirement remains unmet,
and a lower overall spectral loss is not proof of passing it.

The [raw level audit](level-audit.json) finds another remaining defect. Word
output RMS is only **0.5812 times** the original, while its peak is 0.6797 versus
0.5459. Its crest factor is therefore higher. No output gain matching was
applied to hide this: the STOI/spectral measurements' level invariance does not
establish absolute level or waveform fidelity. Excitation shape and low-band
envelopes need further work.

## Actual data cost

[`q4_sparse_stream.py`](../../codec/q4_sparse_stream.py) defines and reads an
exact byte-aligned data representation. An even Q4 half uses the old two Q3
bytes. An odd coefficient adds a parity-mask escape byte, identified through
the previously invalid zero low nibble. Both/low/high/neither coefficient-half
updates are reused exactly. Gain has five bits; its high bit can require an
extended header, alongside pitch, half period and the eight waveform selectors.

[`sizes.json`](sizes.json) measures the serialized endpoints:

| PC endpoint | Frame stream | Eight packed 16-tap waves | Maximum remaining code, before alignment |
| --- | ---: | ---: | ---: |
| Byte states | 728 bytes | 64 EEPROM bytes | 295 bytes |
| Word states | 954 bytes | 64 EEPROM bytes | **69 bytes** |

The last column reserves one EOF byte and assumes all EEPROM is used for the
waveforms. It is a budget remainder, **not measured decoder size**. These
streams cannot be combined with the existing 422-byte decoder within 1 KB;
the word implementation would require separate assembly and qualification.
The source models are quality teachers for a more compact representation.

## Locate the remaining STOI loss

[`band-audit.json`](band-audit.json) decomposes the installed standard STOI into
the actual fifteen third-octave correlations. Their mean is checked against
`pystoi.stoi` to 1e-12, including its resampling and silence removal.

For the word endpoint, the six bands centred at **150–476 Hz** account for
**51.18%** of the remaining gap to 1. Their correlations are 0.796–0.870;
the two highest bands are about 0.915. This suggests prioritizing the trajectory
and levels of the lower harmonics while preserving the other bands. It does
not prove that one frequency or one filter change can recover the whole gap.
Segment indices in the report refer to the signal after silence removal;
they must not be presented as original timestamps or manually labelled phonemes.

A separate [15-case pole/scale screen](tilt-probe.json) keeps the exact timing
and data, tests output poles 0, .5, .75, .875 and .9375, and source scales .5/1/2.
The unchanged .5/unity profile retains the best guarded STOI. A global tilt
change alone is not an improvement and stronger profiles can wrap or exceed
peak/step guards. New coefficients would need their own joint refit.

## Rejected periodic-wave initializer

[`phase-wave/summary.json`](phase-wave/summary.json) retains the configuration
endpoints of a separate source-inverse experiment: complete 32-point periodic
excitation, two/four forms, reset/continuous/aligned phase, previous/source LPC,
word states and both rounding profiles. Pitch/offsets come from the existing
source-only phase analysis; their transmitted values are retained in the model.
It fits waveform proposals by inverse-error analysis, not by the final STOI
objective. Full intermediate epoch logs remain reproducible in ignored build.

Its best selected energy endpoint has STOI **0.640750**, eSTOI **0.479753** and
spectral loss **0.406869**. Raw DC is small and some harmonic metrics improve,
but intelligibility is unacceptable. It is not a representation ceiling or
evidence that full periodic shapes are inherently worse. It is evidence that
this initializer must not replace the successful pulse model without a proper
closed-loop fit.

## Next steps toward 0.93 and 1 KB

1. Continue fitting word-state pulse data, including unbiased rounding; retain
   every qualified endpoint and all absolute errors rather than claiming the
   0.93 goal from a relative gain.
2. Use the band audit to test finer low-harmonic frequency trajectories and
   excitation-envelope control. Check voicing transitions and spectral coverage.
3. Fit compact combinations of voice templates and sparse corrections against
   the teacher and original. Factorized groups or interpolated templates can
   avoid forcing all coefficients to change together. Keep the real data count.
4. Only then optimize and assemble a promising word-state decoder. Measure full
   Flash, EEPROM, SRAM and worst preparation time, compare complete PCM in all
   three engines, and check protected RU/EN examples before selection.

## Reproduction and qualification

The [manifest](manifest.json) pins source revisions, inputs, models and reports.
The full existing suite passes **401 tests** at the core-study revision. This
includes the old AVR qualifications and fourteen new PC format/arithmetic tests;
it does not qualify a new word-state firmware. The subsequently added STOI-band
diagnostic passes three targeted tests separately.
Two further artifact tests reproduce retained PCM, data sizes, STOI, eSTOI,
spectral losses, band scores and all fifteen pole/scale control outputs.

```powershell
python tools/refine-q4-lattice.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q4-voice-patterns/full/per-frame-control.json --output build/q4-lattice/byte-fixed --evaluations 12000 --state-bits 0
python tools/refine-q4-lattice.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q4-voice-patterns/full/per-frame-control.json --output build/q4-lattice/word-fixed --evaluations 12000 --state-bits 4
python tools/analyze-q4-stoi-bands.py --reference web-player/audio/originals/vinni.wav --baseline ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json --teacher ATtiny13A/Sound/research/q4-lattice/word/model.json --output build/q4-lattice/band-audit.json
python tools/probe-q4-tilt.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q4-lattice/word/model.json --output build/q4-lattice/tilt-probe.json
python tools/probe-q4-phase-wave.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json --output build/q4-phase-wave/final-pc --epochs 8 --state-bits 4 --source-phase
python tools/test-speech-quality.py
```

Audio and intermediate binaries remain in ignored `build/`. Public firmware and
the main branch are unchanged. Goal achievement remains unproven.
