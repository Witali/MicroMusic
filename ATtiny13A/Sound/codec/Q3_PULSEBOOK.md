# Q3 EEPROM pulsebook: separate exact excitation profile

This profile replaces the fixed four-sample Q3 source with four selectable
16-sample signed pulses. All64 entries occupy64 EEPROM bytes, in row-major
two's-complement order, with values -7..7. Existing frame mode bits select the
row. Gain multiplies each table value. No new per-frame bits are added.

The oracle is `q3_pulsebook.py`:

```python
pcm_u8, counts = render(frames, durations, pulsebook, tilt_shift=1, nearest=False)
```

Frames/durations are the existing six-field HQ4 arrays. Counts are subtraction
wraps, state-addition wraps, negative128 multiplication and T1 wraps. Every
frame resets the countdown exactly as the old core. When countdown reaches0,
it reloads the period and emits table[mode,0]*gain; following lags1..15 use
their entries, then the source is zero. If the next pulse arrives earlier,
the template restarts there. Unvoiced frames retain the existing binary LFSR
noise. Filter state, signed Q3 coefficient rules, frame timing and T1 persist.

`legacy_tables()` gives the exact four old shapes:
`[2,3-(mode&1),2-(mode>>1),-1,0,...]`. Its PCM and all four audit counts are
byte-exact to the old floor and nearest Q3 decoders. Nearest means
floor((signed_product+4)/8), with original byte-negation behavior. Stable
encoder coefficients exclude -8. No output gain/DC correction is applied.

The separate assembler profile measured408B floor /410B nearest code, leaving
615/613 actual stream bytes plus EOF in1024B Flash. All64 EEPROM bytes are
used by the pulsebook, so they cannot also hold an earlier stream prefix.
`tools/build-q3-pulsebook.py` is the separate hardware-profile builder and
verification entry point; a PC candidate alone is not firmware qualification.

## Automatic fit and joint search

```powershell
python tools/probe-q3-pulsebook.py --reference original7500.wav `
  --model initial.json --model another_seed.json `
  --output build/q3-pulsebook/voice --proposals 6000
python tools/test-q3-pulsebook.py
python tools/test-q3-pulsebook-search.py
```

Schema `hq4-q3-pulsebook-v1` stores `pulsebook`4x16, frames, durations, nearest,
tilt_shift, sample count/rate and reference hash. A model without a pulsebook
starts with legacy tables. Oversized seeds first reuse the closest adjacent
coefficient halves until their actual `pack_stream` fits; duration, pitch,
mode and gain are unchanged in that stage. Those changes and measured initial
quality are reported, rather than silently calling the fitted seed identical.

The joint search mutates all64 table entries and all frame parameter classes:
pitch, gain, mode, coefficients, voiced/unvoiced transitions, duration boundaries
and split/merge structures preserving every sample. Table/gain moves can be
coupled. It does not constrain table sum to zero, so raw mean/RMS remain explicit.
It rejects internal wraps, peak>115 signed DAC units, any sample step>=48 and
oversized streams. It evaluates standard STOI and the complete existing
SpectrogramObjective against the original; it does not impose the old model's
intelligibility or spectral component ceilings.

The absolute joint target is STOI>=.90 and spectrogram_loss<=.344975554.
The search scalar is spectrum+6*max(0,.90-STOI), but exports a non-dominated
STOI/spectrum frontier so the scalar cannot hide the tradeoff. It retains up
to32 frontier points and separately exports balanced/best_stoi/best_spectrum.
Only a model meeting both exact target tests receives `target_met=true`.
Finalists also receive eSTOI and the separate10-track harmonic measurements.

The first6000-proposal Vinni study failed the requested joint target. Its best
STOI was.8404483 and spectrum-only endpoint was.4682765 with STOI.8025357.
This bounded failure neither proves the format incapable nor justifies
publishing it as a quality improvement. Automatically learned inverse-lattice
seeds and subsequent searches must report their own provenance and results.
See `../research/q3-pulsebook/README.md` for the exact first-stage capture.
