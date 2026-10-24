# Structured noise: negative PC screen

No tested nonzero row-noise setting improved either STOI or spectral loss
relative to its own all-off control. The joint 1500-proposal stage was therefore
skipped. No AVR decoder was written, no complete Flash size is known, and
public firmware is unchanged. This result covers this fixed gain/2 two-tap
source and one recording; it does not exclude other noise models.

The screen used the entire Vinni recording: 22,272 unchanged samples at 7500 Hz,
SHA256 `749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
Three existing initializers were deterministically fitted to a conservative
600-byte stream cap: the trimmed 32-tap balanced seed, old public floor Q3 and
the qualified nearest-rounded model. Coefficient reuse is explicit in the
report. Each was tested at quantized gain scales 0.8 and1.0 and all 256 possible
four-row combinations of off/low-pass/high-pass/white noise: 1536 conditions.
Every condition was compared with the all-off state using identical fitted
frames, gain scale and arithmetic. There was no crop, time warp, input/output
normalization or DC correction.

1,350 conditions passed the existing byte-arithmetic/peak/step guards. The
remaining 186 failed: 12 wrap, 48 peak and 126 adjacent-step rejections. All 1,344
valid nonzero-noise conditions worsened **both** STOI and spectrogram loss
against their matched controls. The bounded follow-up gate required a strict
win in both metrics; it found zero, so no follow-up proposals ran.

The best all-off state dominates the whole valid screen. It and the least
damaging nonzero-noise example share exactly the same frames, durations,
signed pulse coefficients and 598-byte speech stream. Only the EEPROM noise
mode differs: `[0,0,0,0]` versus `[0,0,0,1]` (low-pass noise on source row 3).

| Example | STOI | eSTOI | Spectrogram loss | Raw mean | Raw RMS |
|---|---:|---:|---:|---:|---:|
| All off |0.846677|0.650142|0.492748|+0.077355|0.117467|
| Least bad noise |0.832447|0.624822|0.498989|+0.077239|0.117454|

Both examples have zero wrap counters and zero clipped samples; both fail
the strict 5 dB strongest10-partial bound. High-pass/global-RMS spectral metrics
do not demonstrate raw DC correctness. The large positive DC remains.
Neither meets STOI≥0.90 and spectral loss≤0.344975554. The 64-byte encoded
EEPROM image is measured data size; it establishes no decoder or total 1 KB
Flash budget.

`vinni/report.json` retains every control's eSTOI, spectral and matched/raw
partial diagnostics, initial source hashes, coefficient-reuse operations and
normalized source hashes. `screen.csv` contains all 1536 outcomes and rejection
reasons. `summary.json` includes six paired-group extrema and a controlled
example equality check. Only two unique parameter models are retained; the
three best all-off endpoint exports were identical. Original/decoded audio,
raw PCM and packed binaries remain in ignored build output.

Reproduce with the repository codec Python dependencies:

```powershell
python tools/probe-q3-shaped-noise.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-pulsebook32/vinni/initial-6000/balanced/model.json --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --model ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json --output build/q3-shaped-noise/vinni --proposals 1500 --seed 423107
```

`--proposals 1500` is a gated maximum, not a request to run it after a failed
screen. The run exports `balanced/decoded.wav` and
`least_bad_noise/decoded.wav` for listening. Ten tests cover exact all-off
compatibility, fixed signed noise vectors, gain 0/1 LFSR progress, state freezing,
packed modes, raw-value validation, the paired stage gate and valid mutations.
