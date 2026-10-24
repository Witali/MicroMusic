# Learned periodic source with continuous phase: bounded negative result

The selected Q3/T1 final-phrase voice still sounds creaky. This separate PC
experiment replaces its four-sample pulse with automatically learned whole
periodic excitation shapes. It does not repeat the earlier Q4 pulse-dilation
experiment and does not change any selected firmware or retained Q3 model.

The original 12,800-sample voice is passed through an offline floating inverse
of the retained Q3 lattice and T1 stage. Actual original residual cycles are
selected using the control model's period estimates, resampled to 8 or 16
points, aligned at their strongest closure peak and clustered into four
shapes. These period estimates remain a limitation: they are fitted codec
estimates, not independently established reference F0 ground truth. No
frequencies or recording timestamps are picked manually. Each integer source
shape is limited to ±31 and has exactly zero cycle sum.

The two existing mode bits select the learned source. A continuous 16-bit DDS
uses an eight-bit pitch code with `phase += code * 32` and table indexing by
normalized phase. It never resets phase at voiced frame boundaries. Zero pitch
retains the original Q3 LFSR noise path. The exact signed-byte source gain,
eight-stage Q3 lattice, T1 output, sample count and original frame-boundary
convention are preserved. This is explicitly tagged `hq4-q3-phasebook-v1`:
its pitch bytes are increments, so it is incompatible with ordinary Q3 period
data even though the coefficient packing syntax is shared.

The initializer compares both source lengths, automatically selected and old
mode assignments, and four gain scales. DDS pitch-header changes initially
need seven additional stream bytes; minimum-distance coefficient-half reuse
fits the common 430-byte speech budget. The bounded search then makes 1,500
joint frame/pitch/gain/mode/coefficient or zero-sum book-entry proposals,
seed 23203, against the complete original. Unstable Q3 coefficient -8,
intermediate wraps, PWM peaks above 115 and sample steps of at least 48 are
rejected.

| Measurement | Selected Q3/T1 control | Learned source |
|---|---:|---:|
| STOI | .83670 | .75862 |
| eSTOI | .55117 | .39295 |
| Full spectrogram loss | .53779 | .55928 |
| Broad spectral envelope error | .54839 | .60322 |
| Unsupported spectrum energy | .18683 | .20467 |
| Missing spectrum energy | .18965 | .21407 |
| Harmonic p95 frequency error, cents | 66.82 | 57.40 |
| Harmonic p95 level error, dB | 13.88 | 8.30 |
| Harmonic match coverage | .78777 | .75909 |
| Harmonic continuity break rate | .33133 | .08569 |
| Same-time globally matched waveform NRMSE | 1.45835 | 1.33273 |

Lower errors are better; higher intelligibility and coverage are better. The
best candidate uses four 16-point shapes. Waveform error, matched-partial
frequency/level error and continuity improve, but intelligibility, spectral
envelope and missing/unsupported energy worsen. More reference partial energy
also becomes unmatched. **Reject this candidate.** Smoother excitation or a
closer waveform by one metric is not an audible naturalness win.

The final oracle has zero intermediate wraps and preserves all 12,800 samples.
It needs a 430-byte stream plus a 64-byte Flash source table. A coarse source
instruction estimate for a future bell-compatible DDS/LPM core is 550–580
bytes, plus the existing 15-byte bell descriptor and EOF: roughly 1,060–1,090
Flash bytes with this stream. The bell already occupies all 64 EEPROM bytes.
These are engineering estimates only; no assembler profile, timing estimate,
HEX image, three-engine AVR verification or 1-KB fit is claimed. The objective
regression gives no reason to pay for an AVR port.

`codec/q3_phasebook.py` is the exact-byte PC oracle and deterministic offline
book initializer. Four tests check the unchanged noise path, phase continuity
under frame splitting, inverse-lattice recovery of a known source and learned
zero-DC bounds/determinism. The selected compressed model, stream and complete
research report are retained under `tail-voice/`; WAV comparisons and raw PCM
remain in ignored `build/q3-phasebook/tail-voice/`. The comparison order is
original → selected Q3/T1 → rejected learned-source prototype.

```sh
python tools/test-q3-phasebook.py
python tools/probe-q3-phasebook.py \
  --reference build/new-speech/bell-hybrid/voice-reference.wav \
  --model ATtiny13A/Sound/research/hq4-q3-tracks/tail-voice/model.json \
  --output build/q3-phasebook/tail-voice --proposals 1500
```

The prepared original voice/excerpt provenance is described in
`research/natural-timbre/README.md`. The report fingerprints the original,
control model, fitting sources, final compressed model, stream and exact PCM.
