# Nonlinear K1/K2 maps: quality, rate and execution costs

This is the first bounded implementation of plan item1. It does not meet the
absolute STOI.90 / spectrogram loss.344975553560209 targets or replace public
firmware. All experiments preserve the full22,272-sample Vinni reference at
7500Hz, SHA256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.

## Exact format and controls

`hq4-q3-kmap-v1` keeps two4-bit indices for K1/K2 but uses separately fitted
16-entry signedQ7 maps. The other six coefficients remain Q3. Four16-tap
waveforms fit32 EEPROM bytes using offset-by-eight packed nibbles; the maps
occupy the remaining32. `codec/q3_kmap.py` independently packs/unpacks all64
bytes and renders the frozen phase, frame, noise and T1 conventions.

The uniform map maps indices1..15 to the original Q3 values times16. It
reproduces complete old PCM and all four guard counters exactly, with both
rounding profiles. Index0 becomes available only for K1/K2 and must map to a
stable value in−127..127. Other coefficient0 remains forbidden. Signed-byte
negation, including its−128 boundary, is preserved and audited. Five oracle
tests exhaust the signed multiply domains, memory layout and old behavior.

## Automatic fitting

The new fitter screens25 map-offset/gain combinations for each of three old
models, then searches maps, indices, waveforms and all old frame parameters.
No source frequency, timestamp or output equalizer is chosen manually. It uses
the same unchanged full-clip STOI/spectrogram objective and hard arithmetic,
signed-peak115 and step48 guards. Exported metrics include eSTOI, top10 tracks,
strict5dB checks with/without global level matching, raw mean and raw RMS.
HP70 is explicitly part of the spectral/track measurement, not an audio fix.

| Pass / endpoint | STOI | eSTOI | Spectrum loss | Actual stream |
|---|---:|---:|---:|---:|
|6000 proposals, larger-code budget, balanced|.845897|.655620|.492929|590B|
|6000 proposals, spectrum extreme|.796715|.580733|.460491|587B|
|3000 additional proposals, smaller-stream budget, balanced|.836938|.643371|.495243|563B|
|3000 additional proposals, spectrum extreme|.785022|.569289|.462493|557B|

The first pass uses explicit591/587-byte PC capacities and seed23501; the
second uses563/557 and seed23503. The second imports the retained first-pass
balanced/spectrum models and the old base-cycle model, refits their size and
rescored maps without inheriting quality claims. JSON retains complete input,
reference and numerical-source hashes, initialization, search history, final
parameters and fresh checks. Three search tests cover isolated mutations,
actual64-byte export and explicit PC-only flags.

The first generic432/436-byte decoder **failed the sample deadline**: a
separately retained [timing diagnostic](../q3-kmap-generic-timing/README.md)
reproduces the exact binary and5507-sample matching prefix before a1663-cycle
sample computation exceeds1280. A memory fit did not make it playable.

The later stage-selected implementation keeps the fast old Q3 arithmetic for
six stages and Q7 for two. The musical unrolling idea was also implemented
and tested independently; see the [AVR cookbook](../../codec/AVR_ASSEMBLY_RECIPES.md)
and builder's measured tradeoff. Stage-selected code is458/464 bytes; fully
unrolled Q7 is470/474. The direct memory capacities are565/559 and553/549
respectively, including separate EOF/alignment. Each fitted model still needs
its own complete-image timing and PCM qualification.

## Subsequent rate-aware fitting

Simply squeezing the larger-code model by coefficient-distance reuse loses
quality. A separate [output-error-aware rate pruner](../q3-rate-prune/README.md)
compares the same590-byte input at the same563-byte cap. Both endpoints pack
to562 bytes:

| Pruning rule | STOI | eSTOI | Spectrum loss |
|---|---:|---:|---:|
| Old nibble-distance reuse |.833083|.639550|.497559|
| Full decoded-error per saved byte |.842180|.647884|.489369|

The quality-aware result was subsequently qualified with the stage-selected
decoder: **1022 Flash +64 EEPROM**,66,816 identical samples in three engines,
no missed events/overflows, minimum deadline slack135 cycles. Its actual build
is retained with the pruner's research, rather than overwriting this earlier
PC-only search record. This is an improvement of the automatic size-fitting
step, not proof that Kmap beats the best ordinary-codec candidate: that model
has STOI.849533/eSTOI.659937/spectrum.491184 at1014 Flash +64 EEPROM. The
tradeoff is exposed; no universal or subjective naturalness win is claimed.
The raw DC and strict5dB component requirements remain unresolved.

```powershell
python tools/test-q3-kmap.py
python tools/test-q3-kmap-search.py
python tools/probe-q3-kmap.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-core-data-cycles/vinni/cycle-01/after/model.json --model ATtiny13A/Sound/research/q3-pulsebook/vinni/best_spectrum/model.json --model ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json --output build/q3-kmap/vinni-final --floor-budget 591 --rounded-budget 587 --proposals 6000
```

Retained JSON is sufficient to rebuild each exact endpoint without repeating the search; only
parameters/reports are committed, with WAV/raw/binary captures in ignored
`build/`. The smaller code and final rate-pruning tools have independent
sources and tests; see their reports before selecting a profile.
