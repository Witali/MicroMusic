# Tiny Period ideas in LPX: isolated host pilot

**A learned period dictionary is feasible as a separate hybrid mode. This pilot
has not demonstrated a large perceptual improvement that would justify its
additional storage and decoder cost.** A size increase is acceptable when the
quality gain earns it; unchanged stream size is only one comparison scenario.
Production firmware, formats, defaults and arithmetic backends are unchanged.

## What was tried

Tiny Period stores a clip-specific dictionary of complete output-wave periods.
LPX instead applies an LPC filter to excitation. Feeding a complete Tiny speech
waveform through that filter again would repeat spectral shaping. This prototype
therefore learns **inverse-filtered excitation periods**, preserving the actual
quantized LPX spectra, LPC interpolation, scale fields and postfilters.

The isolated LPWB v1 host format stores 32 signed-nibble nodes per period,
continuous 16-bit phase, quantized pitch, gain and differentiated deterministic
noise. A 160-sample block chooses dictionary excitation or the existing LPX
pitch/pulse mode. Actual mixed excitation updates the prediction history;
consecutive dictionary blocks crossfade for 16 samples. The receiver needs only
the serialized stream, not source audio, analysis arrays or fitted phase tracks.

The encoder uses existing Tiny pitch/phase/harmonic analysis at an explicit
8 kHz, then bounded closed-loop integer block search. Dictionaries are trained
on each encoded segment, quantized, made exactly zero-mean, and pruned to active
entries. All headers, dictionaries, phase/mode bits, fallback fields and padding
count toward complete-file size. Eight full entries cost 128 bytes before any
frame data. EEPROM placement would not eliminate this information cost.

Current LPX already exploits periodicity through delayed excitation and pitch
gain: it has an adaptive waveform history without a transmitted static book.
An additional static dictionary must earn its overhead.

This is a project prototype inspired by the general approach in
[Gottesman and Gersho, Enhanced Waveform Interpolative Coding at Low Bit-Rate
(2001)](https://scl.ece.ucsb.edu/sites/default/files/publications/e01_9_0.pdf)
and [Kleijn, Yang and Deprettere, Waveform Interpolation Coding with Pitch-Spaced
Subbands (1998)](https://www.isca-archive.org/icslp_1998/kleijn98_icslp.pdf).
The papers motivate periodic/nonperiodic handling, phase and analysis by
synthesis; their reported quality or bitrate is not a result for LPX.
No paper code or book examples were copied.

## Pilot and controls

Baseline commit: `3680f86c`. Twelve anonymous speech cases, 16 contiguous
segments, 105.067 seconds, six Russian/six English cases, with natural, quiet,
noisy and prepared material. This is a small selected pilot, not the whole
181-case corpus or a held-out evaluation of a shared dictionary.

Both 4/6 profiles used the strongest retained selected v5 stream. Thirty-two
baseline segments were verified against the current native decoder, independent
integer model and saved PCM/PWM. Candidate models used K=4/8, two rate weights
0/.05, and K=0 **zero/noise-only ablation**. The final run fitted 192 streams,
representing 144 joined case/profile/parameter candidates, with 2,823,970
objective evaluations. Original segment joins, levels and full lengths were
preserved; gain fitting and delay fitting were not used.

The original conservative selection scenarios require no increase in
full-reference PCM/PWM SSE and no decrease in available PCM/PWM STOI (absolute
numerical tolerance 1e-10). Existing achieved bytes and configured per-segment
caps are separate budget scenarios. These gates describe the original pilot;
they do not decide whether a larger or mixed-metric candidate is worthwhile.
Baseline v5 remains eligible, and all raw tradeoffs are retained.

## How to judge size for quality

A small size increase with a substantial, demonstrated improvement in sound is
worth retaining, for example as an optional quality profile. A comparable or
uncertain benefit deserves review and further optimization. Do not reject a
candidate solely because its size increased, or require every objective metric
to improve before listening. Retain promising alternatives even while the
current firmware remains the deployed baseline.

Compare the size/quality curve over several budgets. Give the existing encoder
the same extra budget before attributing a benefit to a new mode. Include the
existing 4/6 profiles in the comparison; the pilot did not run an additional
baseline search at each larger candidate's exact size. A point on a frontier
of measured metrics is worth examining, not evidence of an audible win; a
point dominated on those metrics may still sound different.

Report complete stream bytes separately from program Flash, then measure their
combined cost for the intended firmware image. Count code, tables, dictionaries,
headers, alignment and embedded recordings; share common costs once per image.
A one-time decoder cost can be worthwhile across many recordings. Flash, SRAM
and active-interrupt timing limits remain hard constraints for a target build.
The old pilot caps describe particular budgets, not universal research limits.

Do not divide percent size growth by percent SSE reduction and call the result
quality efficiency. SSE, SER in dB, STOI and listening judgments have different
scales. Use absolute STOI changes and SER changes alongside randomized paired
listening with a reference, consistent presentation levels and hidden candidate
identity. Check naturalness, intelligibility, artifacts and preference over both
whole clips and changed regions. These are proposed project checks, not a claim
that this pilot followed a standardized subjective test. See
[ITU-T P.800](https://www.itu.int/ITU-T/recommendations/rec.aspx?rec=3638) for
formal subjective evaluation procedures and
[Taal et al. (2011)](https://doi.org/10.1109/TASL.2011.2114881) for STOI as an
intelligibility predictor. No listening scores were collected in this pilot.

## Result

- Under achieved stream sizes, selection retained v5 in 23/24 case/profiles.
  The remaining result is reproducible by K=0 alone. Its 1084 to 1000 byte
  reduction uses 20 silent blocks and **zero active learned periods**.
- Under configured caps, selection retained v5 in 22/24, chose that same
  ablation once, and chose K4 once.
- The distinct learned-period result activates only two blocks. It improves
  PCM SSE by about 0.1025% and slightly improves both STOIs, but grows the
  existing stream from **23262 to 25272 bytes** (+2010, +8.64%). This is a tiny
  metric improvement with a data cost. Keep it for listening; the size increase
  alone does not disqualify it. Decoder Flash has not been measured.
- Rate penalties can reduce bytes, with quality losses on other candidates.
  Of 144 raw candidates, 26 passed all quality floors, three also fitted
  achieved bytes (the same silence-equivalent output), and 21 fitted configured
  caps, including baseline-equivalent results with extra data.

Totals below cover all twelve cases. SSE is in billions; STOI is a case mean,
not a listening score.

| Profile | Variant | Complete bytes | PCM SSE | PCM STOI |
| --- | --- | ---: | ---: | ---: |
| 4 | Existing v5 | 47876 | 1170.305 | .719741 |
| 4 | K4, weight0 | 52530 | 1194.375 | .693852 |
| 4 | K8, weight0 | 52046 | 1223.889 | .671065 |
| 6 | Existing v5 | 68427 | 793.519 | .763628 |
| 6 | K4, weight0 | 72133 | 796.511 | .732133 |
| 6 | K8, weight0 | 71651 | 795.244 | .724727 |

[summary.json](summary.json) retains source/dependency hashes, protocol,
aggregates and decisions. [case-results.csv](case-results.csv) preserves all
168 baseline/candidate rows, including spectral/PWM metrics, byte accounting and
active-period counts. Fitted dictionaries, source paths, audio, payloads and
raw private manifests stay in ignored local build folders.

## Reassessment allowing size growth

[tradeoff-review.json](tradeoff-review.json) re-evaluates the same published CSV
without re-encoding or changing the historical report. Against the matching
baseline profile, four of the 144 candidates have at least one gain and no
regression across PCM/PWM SSE/STOI (including three silence-equivalent variants).
There are also 24 mixed results, 22 metric ties and 94 results with a degradation
and no gain.
These are numerical categories, not listening outcomes or quality percentages.

Sixteen candidates grew and improved at least one of these metrics; one improved
all four. They remain explicit review candidates, including those outside the
old caps. A surrogate frontier over complete bytes and those four metrics,
across both 4/6 profiles for each reference, contains 78 of the 168 measured
points, including ties. That count does not establish 78 perceptual winners.

| Case / profile / variant | Extra bytes | Size change | PCM SER change | PCM STOI change | PWM STOI change |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10 / 6 / K4 weight0 | 2010 | +8.64% | +0.00445 dB | +0.0000234 | +0.0000357 |
| 01 / 4 / K4 weight0 | 362 | +10.00% | -0.39780 dB | +0.0044607 | +0.0032397 |
| 07 / 4 / K4 weight0 | 480 | +13.17% | +0.02220 dB | -0.0016878 | -0.0014179 |

The first remains a candidate with a small measured gain; its perceptual value
is unknown. The second has the largest PCM STOI increase among growing
candidates but greater waveform error. The third illustrates why lower SSE
alone does not settle the decision. Listen to these tradeoffs before deciding
whether their sound justifies extra bytes. The current evidence supports
neither a large audible improvement nor automatic rejection for size growth.

## Status and next design choices

Thirteen synthetic test groups pass: native legacy parity, independent
phase/noise/mixed arithmetic, strict container validation, partial/max tails,
roundtrip, deterministic fitting, stale-analysis rejection and validation even
when analysis is reused. The active LPX source tree is unchanged.

LPWB is **host research only** and is not accepted by the active firmware.
No AVR Flash/SRAM/cycles or active-IRQ admission is claimed for this new format.
The pilot does not yet establish whether the audible benefit would justify
paying for a second firmware parser/generator. Preserve the prototype and its
size/quality alternatives for that evaluation. File-byte results cannot be
substituted for total firmware measurements.

This first fitter freezes LPC spectra and uses a greedy 20 ms horizon with
limited phase/gain proposals. Broader joint phase/dictionary/spectrum search
could change the result. Direct Tiny output periods with a separate LPC bypass
are another untested design: switching, filter state and consonants must be
designed together. Naturalness requires listening alongside numeric metrics;
no human ratings were collected here.

## Reproduce

Use the existing LPX Python requirements and a native C++ compiler. Put active
LPX tools/tests plus this study's prototype/tests on the import path through:

```text
python Codecs/LPX/research/period-excitation-2026-10-27/run.py test
python Codecs/LPX/research/period-excitation-2026-10-27/run.py benchmark PRIVATE_MANIFEST build/period-pilot --limit-cases 1
```

Remove `--limit-cases` for the complete private pilot. The input schema is
`lpx-period-pilot-private-v1`; original references/caches are required and are
not distributed here. The benchmark restricts generated artifacts to ignored
repository build storage and writes anonymous reports. No optimization replaces
a baseline automatically. The numerical and native environment is fingerprinted
with each run.
