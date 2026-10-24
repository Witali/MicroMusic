# Actual Q3 compression controlled by partial-track error

`tools/compress-hq4-q3-tracks.py` reduces the serialized speech stream, rather
than merely changing a fitting weight. It starts from an explicitly tagged
`hq4-q3-v1` model of the complete original recording. Candidate operations share
four/eight reflection coefficients across frames or runs, merge adjacent
frames whose combined duration is at most 256 samples, and opportunistically
refit shared coefficient groups. Only an actually smaller `pack_stream` result
can replace the current model. Every sample and the total duration remain.

The exact integer Q3 decoder evaluates each candidate. Intermediate lattice and
T1 arithmetic wraps, PWM peaks above 115, and adjacent sample steps of at least
48 reject it. The strongest ten original spectral partials are cached once.
Their actual decoded frequency and amplitude errors supply the rate bounds.
No reference frequencies, analysis time or harmonic matching gates are moved
when the user changes a tolerance.

## What a tolerance bounds

The default `--error-statistic p95` bounds the 95th percentile of **matched
original-partial power**. It does not bound every instantaneous peak and it
does not imply that all original partials were matched. `mean` bounds the
power-weighted mean; `max` bounds every matched partial. Missing reference
energy, extra candidate energy, match coverage and continuity breaks always
remain within the original input model's measured limits. Thus a difficult
partial cannot simply be dropped to improve the reported matched error.

Frequency bounds use cents or Hz; amplitude bounds use dB. Matching has its
own fixed one-to-one frequency gate and is independent of these tolerances.
Global RMS matching removes only one overall playback-level difference, so
the amplitude constraint concerns the time-varying partial balance.

By default, caps describe absolute deviation from the original. If an existing
codec already violates strict caps, the report truthfully marks that result
infeasible; it does not relabel the old error as zero. `--relative-to-baseline`
explicitly permits the stated **additional** error above the frozen input
model's error. The latter mode is useful for controlling how much quality an
already compressed recording may lose. Its reports are labeled accordingly.

Looser frequency/amplitude caps can permit smaller streams, but harmonic
tracking alone does not guarantee intelligibility. Every exported level also
reports STOI, eSTOI and complete spectrogram metrics. Add `--minimum-stoi` or
`--maximum-stoi-drop` to preserve an independent intelligibility floor. These
optional guards are unset in a pure frequency/amplitude-versus-size sweep.

## Examples

```sh
# Absolute-original caps; default power-weighted p95 statistic.
python tools/compress-hq4-q3-tracks.py \
  --reference original.wav --model voice-q3.json --output build/rate \
  --frequency-tolerance-cents 100 --amplitude-tolerance-db 16

# A hard bound on every matched partial, with a separate STOI floor.
python tools/compress-hq4-q3-tracks.py \
  --reference original.wav --model voice-q3.json --output build/rate-max \
  --frequency-tolerance-hz 30 --amplitude-tolerance-db 8 \
  --error-statistic max --maximum-stoi-drop .01

# A sweep of ADDITIONAL p95 error over the frozen original input codec.
python tools/compress-hq4-q3-tracks.py \
  --reference original.wav --model voice-q3.json --output build/rate-relative \
  --sweep 0:0,25:1,75:2 --frequency-unit cents --relative-to-baseline
```

In a sweep both caps must increase monotonically. Each looser level retains
the previous selected model as its seed, so serialized bytes cannot increase.
A search can plateau; no reduction is promised for every tolerance increment.
`--max-evaluations` bounds exact candidate checks at each level, while cached
decoding/track results are reused across levels. A fixed seed makes the bounded
proposal order reproducible.

Each level exports a compressed frame model, speech stream, decoded PCM/WAV,
tracking limits and errors, complete spectrogram diagnostics and actual byte
counts. Reports separate code, speech, end marker, bell descriptor and EEPROM.
Computed Flash sizes include word alignment. `--layout bell` accounts for the
576-byte Q3/T1 bell core, 15 descriptor bytes and 64 EEPROM bytes; it does not
assemble or invent a new bell fit. Use `tools/build-q3-bell-hq4.py` for that
qualification. `--build` qualifies only the final feasible standalone model
through the existing three-engine AVR verifier.

The retained [bounded example sweeps](../research/q3-track-rate/README.md)
demonstrate real size/quality tradeoffs. They are compression experiments;
they do not replace the selected highest-quality listening examples.
