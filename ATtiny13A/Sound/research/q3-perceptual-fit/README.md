# Bounded perceptually weighted lookahead fits

**Neither experiment meets STOI >= .90 and spectrogram loss <= .3449755536.**
The new encoder path did not produce a qualified quality improvement. The
useful confirmed result is compile-profile selection: the cycle02 data never
uses the exceptional pole coefficient, so its exact PCM can use the ordinary
392-byte compact core, freeing 22 Flash bytes.

## Method and limits

The encoder builds a deterministic beam over four neighbouring frames, with
two offset forward/reverse passes and width six. It composes pitch, gain and
mode choices before deciding whether to accept the complete trajectory.
Correlated coefficient proposals also edit complete existing reuse runs.
This differs from the preceding random and greedy single-coordinate searches.
It keeps all source samples, durations and the existing pulsebook arithmetic.

Two cheap rankings are derived automatically from the original: order-eight
LPC-weighted complex residual energy and LPC-weighted log-magnitude error.
The weighting has power response
`|A(gamma1*z^-1)/A(gamma2*z^-1)|^2`, with gamma1=.92 and gamma2=.6.
This is a Speex-style analysis-by-synthesis proposal guide, not a Speex CELP
port. The constants are an explicitly recorded experiment variant; examples
of Speex weighting also use gamma1=.9. There are no phrase-specific frequency
bands, notches, manually selected pitches, output normalization or DC repair.

Every guide trial renders the **whole exact clip from reset**. Lattice,
excitation, phase, noise and T1 states carry through all frames. No independent
PCM blocks are joined. The guide sees 512 samples of context on each side of
the trajectory. Each beam endpoint then gets the unchanged full-duration
STOI/spectrogram objectives, real `pack_stream` size, all four wrap counters,
signed peak <=115 and zero steps >=48. Temporary beam prefixes may exceed the
real capacity by four bytes; an accepted endpoint cannot exceed it.

The existing target scalar selects an exploratory branch, so its internal
`accepted_blocks` is not a quality qualification. All final endpoints are
rescored from a fresh oracle render and audited for deterministic eSTOI and
every selected original partial's raw/level-matched 5-dB error, with missing
partials counted as violations. The retained reports expose the failed checks.

## Measurements

Same unchanged 22272-sample, 7500-Hz Vinni reference in both runs, SHA256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
The configured maximum is 500 exact evaluations. Each complete two-pass
schedule exhausts its finite block list sooner, at 396/395 actual endpoints.

| Run / endpoint | STOI | eSTOI | Spectrogram loss | Stream bytes |
|---|---:|---:|---:|---:|
| cycle02 start, exact ordinary-core conversion | .8475091223 | .6597706434 | .4936535123 | 608 |
| first beam, balanced/STOI | .8475127826 | .6597402410 | .4936297225 | 608 |
| first beam, spectrum extreme | .8390160947 | .6257134118 | .4920776419 | 608 |
| stronger 32-tap fit, exact zero-tail conversion | .8495328544 | .6599372468 | .4911844212 | 620 |
| second beam, balanced/STOI | .8495328544 | .6599372468 | .4911844212 | 620 |
| second beam, spectrum extreme | .8455444610 | .6526858133 | .4891814009 | 620 |

The first beam evaluated 18473 valid cheap guide trials and 396 exact
endpoints. One accepted two-frame change makes a negligible STOI/spectrum
gain, but **eSTOI falls** and level-matched strict violations rise from1125
to1127. It is rejected as a quality improvement. Its raw mean remains+.07726;
no measurement output is secretly high-passed or recentred.

The second beam evaluated 18405 valid guide trials and395 exact endpoints,
accepting no block. It retains the stronger input unchanged. The best
spectrum-only alternatives in both runs reduce intelligibility. Raw/level-
matched strict partial checks fail for all final candidates. This rejects
this finite guide/beam configuration; it does not establish a codec upper
bound or show that all perceptual weighting strategies are ineffective.

## Exact core and source selection

`cycle02-start/before/model.json` is an explicit conversion from the separately
tagged pole format. There are zero exceptional nibbles. Both frozen numerical
oracles produce identical22272 PCM bytes **and all four internal counters**.
Only the schema changes; frames, durations and all64 table values are identical.

The converted baseline was subsequently assembled with the frozen ordinary
compact builder and run in three engines. Actual memory is392 code +608
stream +1 EOF +1 alignment = **1002 Flash bytes /64 EEPROM bytes**. All66816
samples match (full phrase followed by2N midpoint silence); minimum deadline
slack is332 cycles, with no missed events or arithmetic wraps. The previous
pole image was1024 bytes. Its sound quality is unchanged by this22-byte saving.
`cycle02-start/before/avr/build.json` and `verification.json` retain the proof.

The stronger seed came from the separate automatic32-tap source experiment.
All lags16..31 of that fitted book are zero. The new `--trim-zero-tail` option
requires the tagged32-tap schema, rejects any active removed tap, and asserts
full exact PCM, all four counters **and packed-stream equality** against the
frozen16-tap oracle. This removes unused features before fitting under the
ordinary631-byte real stream capacity. Its quality gain over cycle02 belongs
to that separate earlier fitting experiment, not to this beam search.

This stronger converted seed was also assembled with the ordinary compact
core:392 code +620 stream +1 EOF +1 alignment = **1014 Flash /64 EEPROM bytes**.
Again, all66816 samples are exact in three engines, silence is verified, there
are no lost/missed events, and minimum deadline slack is332 cycles. Its
`stronger32-start/before/avr/` reports retain that independent qualification.

Raw captures conservatively say `avr_verified=false` because fitting precedes
candidate assembly. Subsequent independent qualification is recorded
separately, without rewriting captured training history. New spectrum-only or
eSTOI-regressing beam endpoints were not selected for firmware publication.
No physical hardware testing is claimed.

## Artifacts and reproduction

`cycle02-start/` and `stronger32-start/` preserve each raw report and the
before/balanced/STOI/spectrum parameter models, packed streams and quality
checks. The duplicate balanced/STOI exports are intentional named captures
from the generic runner. Source fingerprints, exact block order and every
accepted trajectory are retained. Original WAV, decoded WAV, EEPROM binary,
PCM and compiled images remain in ignored `build/q3-perceptual-fit/`.

The first report was captured with source commit `953af97`. The second adds
only the explicit zero-tail conversion/helper test in `39ec31c`; the beam
numerics are unchanged. Nine focused tests cover LPC silence/periodicity,
identity/error scoring and full-duration enforcement, exact frame boundaries,
dual-guide diversity, crossing a rejected single-prefix barrier, correlated
reuse preservation, joint source choices, both unused-feature conversions
and rejection of active removed features.

Run from the worktree root with the bundled Python dependency paths configured:

```powershell
python tools/probe-q3-perceptual-fit.py --reference web-player/audio/originals/vinni.wav --model build/q3-core-data-cycles/vinni/cycle-02/after/model.json --core-report build/q3-pulsebook-compact-validation/maximum/True-False-avr/build.json --ordinary-core-report build/q3-pulsebook-compact-validation/maximum/False-False-avr/build.json --output build/q3-perceptual-fit/vinni
python tools/probe-q3-perceptual-fit.py --reference web-player/audio/originals/vinni.wav --model build/q3-pulsebook32/vinni/initial-6000/balanced/model.json --core-report build/q3-pulsebook-compact-validation/maximum/False-False-avr/build.json --trim-zero-tail --output build/q3-perceptual-fit/vinni-stronger
python tools/test-q3-perceptual-fit.py
```

Actual core reports and their compiled image hashes are required by the runner,
not inferred capacities. Rebuild them with the existing compact builder if
ignored build artifacts are absent. Public sources/firmware remain unchanged.

## Raw listening artifact

`build/q3-perceptual-fit/listening/index.html` provides individual audio and
`04-comparison-raw.wav` in this order: original, actual previouscycle02,
actual strongerbalanced. The original file is copied byte-for-byte and each
firmware WAV preserves the exact unsigned8-bit DAC samples. The sequential
FLOAT32 WAV adds only two2250-sample zero pauses. Its71316 stored samples and
the individual WAVs are read back and asserted exact. Levels and DC remain
unchanged; no highpass, RMS match, gain, clipping or smoothing is used.
The metadata are retained in `listening.json`, including source firmware,
PCM and WAV hashes, segment offsets and the generator's source fingerprint.

The generic raw comparison generator is source commit `9b93ee2` and requires
matching actual images/EEPROM/capture hashes, three successful engines,
unchanged full phrase length and verified2N midpoint silence:

```powershell
python tools/render-q3-raw-listening.py --reference web-player/audio/originals/vinni.wav --previous build/q3-core-data-cycles/vinni/cycle-02/avr --current build/q3-perceptual-fit/vinni-stronger/before/avr --output build/q3-perceptual-fit/listening
```
