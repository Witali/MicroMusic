# Quality-aware reuse of Kmap speech coefficients

The new encoder preserves more intelligibility at the **same562-byte stream**
than the old coefficient-distance pruning. This is a measured improvement of
the rate-fitting step. It does not beat the separate best620-byte balanced
speech candidate, and it does not meet STOI>=.90 / spectrum<=.3449755536.
Public firmware remains unchanged.

## Controlled comparison

Both paths start from exactly the same590-byte Kmap model, unchanged22272
samples at7500Hz, with fixed pitch, gain/mode, frame durations, waveforms,
K1/K2 maps and arithmetic. Only complete two-byte coefficient halves are
replaced by the previous frame's half. The old and new methods enumerate the
same packet-copy family, and the actual packer decides whether bytes are saved.
A later retransmission can cancel a nominal saving; those proposals are excluded.

| Model | Actual stream B | STOI | eSTOI | Spectrogram loss |
|---|---:|---:|---:|---:|
| Original Kmap input |590|.8458974452|.6556203213|.4929287470|
| Old nibble-distance pruning |562|.8330830151|.6395499671|.4975593336|
| New decoded-quality pruning |562|.8421804000|.6478840281|.4893688771|

Thus the new562-byte result has better STOI, eSTOI and spectrum than the matched
old562-byte control. Against its larger590-byte input it loses.003717 STOI
and.007736 eSTOI while reducing spectral error. These are separate comparisons;
the result is not presented as a universal quality improvement or a natural
voice matching the original.

The final peak is100 signed DAC units. Both controls and the input have zero
internal wraps, negative128 multiplication hazards and sample steps>=48.
New raw mean is+.075960 versus+.077748 for old pruning and+.077154 for input.
There is no hidden DC repair, rescaling or clipping. Strict5-dB selected-partial
checks still fail: raw-level violations1331 versus1333 for old pruning;
RMS-matched violations1110 versus1115. Missing partials count as violations.

## Algorithm and capacity rule

The old `fit_budget` chooses the smallest nibble-distance/saved-byte ratio.
Indices into nonuniform Q7 maps are not a uniform coefficient or resonance
distance. The new tool uses three rankings only to create a diverse shortlist:
legacy nibble distance, `atanh` distance of the decoded stable reflection
coefficients, and the actual full-decoder spectral loss change per saved byte.
It interleaves these lists to select12 proposals per step. The `atanh` guide
is a heuristic, not a final error metric.

Every shortlisted proposal then gets **full exact STOI and the frozen full
spectrogram objective**, after whole-clip decoding with all carried lattice,
phase/noise and T1 states. It chooses the smallest increase in the existing
target energy per actual saved byte:
`spectrogram_loss + 6*max(0, .9-STOI)`. Arithmetic, peak and step guards must
hold. No original PCM, independent synthesized chunk, frequency mask or
phrase-specific manual correction reaches the decoder.

The crucial intermediate capacity is the **original590 bytes**, not the final
target563. Otherwise the first reduction588B would be rejected before a
multi-step route could reach the smaller target. Only the final endpoint must
fit563. The actual finished stream is562B; the fixed pitch/duration headers
and coefficient-half updates in this input give an even stream length.

The bounded run completes13 steps, considering1307 real byte-saving proposals.
1268 pass preview guards and get a full decoded spectral guide;39 are rejected
by arithmetic/peak/step guards. It computes156 full STOI+spectrogram trials,
below the3000 configured limit. An exhausted budget or lack of a safe saving
is reported as an incomplete endpoint rather than a false fit. Shortlist0 can
evaluate every safe proposal; this retained run uses12 and claims no global
rate-distortion optimum. Final eSTOI, strict partial checks, DC/RMS and all
original objectives are recalculated independently of the guide.

## Subsequent assembled qualification

The raw capture first records PC capacity only. The quality-aware562B output
was subsequently assembled using the separately implemented stage-selected
Q3/Q7 Kmap core (source/builder commit`978bf56`):458 code +562 speech +1 EOF
+1 alignment = **1022 Flash bytes**,
with **64 EEPROM bytes** (32 packed waveform bytes and32 coefficient-map bytes).
The measured profile capacity is565B, so the retained563B fitting target was
conservative. This later capacity observation does not alter the comparison.

Reference, WASM and unoptimized WASM engines agree on all66816 output bytes:
the full22272-sample phrase plus44544 verified midpoint-silence samples.
There are no missed samples or lost overflows. Minimum deadline slack is135
cycles at9.6MHz/7500Hz. The generated FLOAT WAV also equals the actual AVR
phrase sample-for-sample. Physical hardware testing is not claimed. The old
pruning control is a numerical reference and was not separately assembled.

`vinni-563/qualification.json` and `quality-aware/avr/{build,verification}.json`
record this later proof. Raw PC reports retain their original `avr_verified`
false values, preserving the order of fitting and qualification. The actual
image SHA is`63f79bb93a4f5b1e6eb0bab94412409e373ae35bb2f80497517f42694ecf5334`.

## Reproduction and artifacts

The source is commit`9f8f5d6`: `tools/probe-q3-rate-prune.py` and six focused
tests. Tests cover true packer savings, quality beating the nearest nibble,
original-capacity intermediate states, honest budget exhaustion, guard
rejection and decoding Q7 maps before measuring resonance-sensitive distance.
Frozen older searches and numerical decoders were not edited.

`vinni-563/before/model.json` retains the exact input file, matching the source
model hash in `report.json`. Before/control/new models, packed streams, final
checks, complete chosen-reuse history and source/reference fingerprints are
retained. `retention-validation.json` records fresh full STOI/eSTOI/spectrum
agreement within1e-12, exact pack/unpack parameters and confirmation that pitch,
gain/mode, timing and all tables are unchanged. Raw PCM/WAV, EEPROM binaries
and compiled images stay in ignored `build/q3-rate-prune/`.

```powershell
python tools/probe-q3-rate-prune.py --reference web-player/audio/originals/vinni.wav --model build/q3-kmap/vinni-final/balanced/model.json --output build/q3-rate-prune/vinni-563 --target-budget 563 --max-evaluations 3000 --shortlist 12
python tools/test-q3-rate-prune.py
```

The reference SHA256 is
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.

The optional local page`build/q3-rate-prune/listening/index.html` has individual
clips and`04-comparison-raw.wav`: original -> old562B prune -> new562B prune.
The71316-sample FLOAT comparison contains only the three unchanged-level/DC
phrases and two2250-sample zero pauses; its WAV roundtrip is exact. No highpass,
RMS matching, gain or clipping is applied. `vinni-563/listening.json` retains
audio/segment hashes; the later qualification ties the new clip to actual AVR
output. The old clip remains explicitly a PC numerical control.
