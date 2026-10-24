# Bounded voiced-source pulse experiment: rejected

The current HQ4 source uses four samples `[2, 3 or 2, 2 or 1, -1]` times
frame gain for a voiced period. Its approximately 0.53-ms width is independent
of the pitch period. A narrow source pulse is a plausible contributor to a
bright harmonic comb, but that observation alone does not establish the cause
of the reported squeaky voice.

`codec/hq4_excitation.py` tests source changes before the exact signed eight-bit
lattice: hold each pulse sample for 1, 2 or 4 samples, and optionally remove
the final negative sample. Unvoiced LFSR excitation, frame timing, pitch-period
length, mode bits and coefficient data format remain unchanged. Each profile
also tests either ordinary output or the existing T1 output state. This is a
PC-only experiment. No candidate was sufficiently good to justify AVR assembly,
timing qualification or a replacement firmware.

The search initially evaluates all 12 source/output profiles against both the
current T1 and ordinary-HQ4 streams, with four global gain scales. It shortlists
the best changed-pulse profiles using `STOI - .12 * legacy spectral loss`, then
jointly refits pitch, gain, mode, reflection coefficients and frame durations.
Vinni received 2,000 proposals for each of three profiles, seed 23160. The
12,800-sample final-recording voice received 1,000 proposals for two profiles,
with the same seed. Every sample and the complete recording duration remain.
Vinni's legacy 406-byte decoder size is the starting budget; variant instruction
counts are engineering estimates only. Voice candidates receive a generous
standalone budget, not the tighter combined bell-plus-voice budget.

| Recording / profile | STOI | eSTOI | Legacy log spectrum | Broad envelope | Unsupported energy |
|---|---:|---:|---:|---:|---:|
| Vinni, current T1 control | .84538 | .66704 | .67857 | .67161 | .26078 |
| Vinni, remove final spike, T1 | .83472 | .64295 | .61113 | .69697 | .26502 |
| Vinni, remove final spike, ordinary output | .83862 | .65596 | .72420 | .68704 | .26938 |
| Vinni, pulse twice as wide, ordinary output | .80909 | .59549 | .67794 | .74661 | .30590 |
| Final voice, current T1 control | .82508 | .51995 | .80218 | .68035 | .27052 |
| Final voice, remove final spike, T1 | .81912 | .51052 | .79445 | .71059 | .27472 |
| Final voice, remove final spike, ordinary output | .81982 | .48821 | .80094 | .66582 | .27212 |

Lower spectral distances and energy errors are better. All shortlisted
candidates weaken STOI and eSTOI. For Vinni, removing the negative spike reduces
fine log-spectrum error but increases both missing and unsupported energy and
worsens the broad spectral envelope. It is an example of why a single improved
scalar spectral loss is insufficient. The widened pulse worsens the broad
envelope and unsupported energy even after joint parameter fitting. None is
selected. Original T1 and public source models remain intact.

The additional structural measurements use `codec/spectrogram_objective.py`:
256/1024-sample STFTs and 32 mel envelopes, common 70-Hz highpass and one global
RMS match. The report fingerprints that independent evaluation source. These
measurements were added after the pulse search; they did not guide its proposal
selection. Per-recording reports retain every initial trial, final metrics,
compressed candidate models/streams and source/reference hashes. Full search
trajectories and WAV comparisons remain under ignored `build/excitation-width/`.
The rejection is limited to this bounded search and these pulse families.

## Reproduce

```sh
python tools/test-hq4-excitation.py
python tools/probe-hq4-excitation.py \
  --reference web-player/audio/originals/vinni.wav \
  --stream ATtiny13A/Sound/research/natural-timbre/public-vinni/speech.hq \
  --alternate-stream ATtiny13A/Sound/codec/release/vinni/speech.hq \
  --output build/excitation-width/vinni --proposals 2000 --shortlist 3
```

For the final recording, use the prepared voice reference described in
`research/natural-timbre/README.md`, `natural-timbre/tail-voice-430/speech.hq`
as the current stream, and `natural-timbre/baseline-voice/speech.hq` as the
alternate. Set `--proposals 1000 --shortlist 2`. The tool reports the unchanged
T1 profile as selected unless a candidate improves legacy spectrum while
preserving both intelligibility floors. No listening or naturalness win is
claimed for these rejected alternatives.
