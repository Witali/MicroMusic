# Prospective octave-observation floor

This addendum was specified after the public tuning pilot and before any new
primary encoding. The 12 source identities and all 24 prepared targets stay
fixed. No new-primary output informed this change.

The pre-guard public pilot added one near-half-pitch observation per PCM/PWM
path in a P6/8-kHz case. It extended an already existing subharmonic episode
by one 20-ms hop: the former output was ambiguous in that window, rather than
a correct pitch match. The existing net-match safety rule did not detect this.
The public result and its tradeoffs remain in `public-final-v3.json`.

## Additional production floor

The new joint-refinement stage retains the complete current-V3 incumbent and
its unchanged multi-metric objective. It additionally rejects a candidate
with a new half- or double-pitch label in any fixed source window, in either
PCM or mapped-PWM output. The comparison is per window, rather than just a
whole-file count. A label already present in the same incumbent window is
permitted. Ambiguous-to-octave transitions are rejected too.

Use the existing period-observation definitions at the actual 8/12/16-kHz
rate, without resampling, alignment or output gain fitting:

- Complete 80-ms windows at 20-ms hops, starting at sample zero; no edge padding.
- Mean removal and amplitude scaling only inside temporary analysis.
- PCM16 RMS floor 0.5; candidate frequency range 50–800 Hz.
- First local CMND trough strictly below 0.15, with the existing raw-difference
  quadratic interpolation and half-sample offset clamp.
- A half-pitch label is within 100 cents of half the source observation; a
  double-pitch label is within 100 cents of twice that observation.
- The source and output must both have finite observations for an octave label.
  Source-ambiguous windows impose no octave label; all original quality and
  collapse floors still apply independently.

These are the already frozen `PitchSettings`/`track_pitch` definitions from
`tools/voice_character.py`. `LpxPitchGuard` uses the native-rate
`estimatePeriod` overload and caches source and incumbent labels. The guard
does not alter decoder code, stream syntax, byte caps, score weights or
zero-loss behavior. It is a conservative periodicity-observation floor, not
a validated fundamental-frequency or perceptual model.

## Independent verification and run provenance

The existing Python `pitch_tradeoffs.py` recomputes the same source-frozen
windows and reports `new_half_pitch` and `new_double_pitch` as mask additions.
Both must be zero for each output path in the guarded study. Lost/gained
100-cent matches, missing observations and all original metric tradeoffs
remain reported independently.

Preserve the original source-preparation manifests and their digests. Bind this
addendum, the final algorithm source freeze and the actual candidate binary in
the private run metadata before launching primary jobs. Existing unguarded
public receipts remain unchanged and must not be relabeled as guarded output.
