# Controlled frequency-versus-amplitude fitting experiment

`tools/probe-hq4-q3-influence.py` compares three automatic Q3 fits: frequency
priority `(1, 0)`, amplitude priority `(0, 1)`, and balanced `(0.5, 0.5)`.
They share one frozen input model, reference audio, byte budget, proposal count,
and a common per-step random schedule. Each step has independent precomputed
proposal/reuse seeds and anchor/acceptance draws. Different acceptance decisions
cannot advance or otherwise desynchronize the later random schedule. Model
trajectories can still diverge, as expected when changing an objective.

All frame fields remain searchable through the existing joint proposals: eight
coefficients, gain, pitch/voicing, four excitation shapes, boundaries and
split/merge. No source frequency or interval is selected manually.

Each objective component is divided by its value in the same frozen baseline:

```
S = spectrogram_loss / baseline_spectrogram_loss
F = 0.70 * trajectory_error / baseline_trajectory_error
  + 0.15 * missing_track_energy / baseline_missing_track_energy
  + 0.15 * extra_track_energy / baseline_extra_track_energy
A = level_error / baseline_level_error

objective = 0.50 * S + 0.50 * (frequency_weight * F + amplitude_weight * A)
```

Thus every profile starts at objective 1, has the same spectral weight, and
compares relative changes instead of mixing arbitrary Hz and dB units. The
combined harmonic loss from the shared diagnostics is not an eligibility guard
or selection target. Its cached `difference_loss` field is diagnostic only;
`normalized_objective` identifies the actual profile-specific target.

STOI/eSTOI remain hard floors. The four spectrogram components, tracked missing
and extra energy, and continuity-break rate cannot worsen; weighted coverage
cannot decrease. Physical sample, Flash-data, arithmetic-wrap, and PWM guards
are unchanged. Infeasible working states may be explored, but only feasible
elites are exported.

The report records absolute Hz, cents, dB, p95 errors, coverage, spectral and
intelligibility measurements, accepted elites, schedule/input/source hashes,
and stream/PCM/audio hashes. All five matched listening parts use a common
filter, RMS target, and final gain: original → frozen baseline → frequency
priority → amplitude priority → balanced. A profile that does not change the
packed stream is explicitly identified as unchanged.

This is a local, bounded encoder ablation under a fixed memory/decoder budget.
No accepted steps means search stagnation under those guards. It does not mean
frequency or amplitude is unimportant to human perception, and it does not
estimate a universal perceptual weighting. Human listening and a separate
controlled signal perturbation are needed for that broader question.

Example:

```powershell
python tools/probe-hq4-q3-influence.py --reference build/new-speech/bell-hybrid/voice-reference.wav --model ATtiny13A/Sound/research/hq4-q3-tracks/tail-voice/model.json --output build/hq4-q3-influence/tail-voice --proposals 1500 --stream-budget 430
```

`tools/test-hq4-q3-influence.py` checks independent frequency/amplitude weights,
the guard distinction, and identical proposal random recipes even when the
weighted acceptance decisions diverge.
