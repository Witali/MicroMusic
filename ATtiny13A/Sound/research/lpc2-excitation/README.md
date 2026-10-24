# LPC2 predictor and encoded-excitation study

The user subsequently restored a hard limit of **1024 Flash bytes including
the decoder, plus 64 EEPROM bytes**. This larger PC study remains a quality
reference; these containers do not satisfy that firmware budget.

This study follows the user's removal of the 1 KB limit. The target is a more
natural voice while retaining a measurable size/quality tradeoff. These are
numerical PC decoders with complete data containers, not AVR firmware.

The reference encoder is the exact retained LPC2 Improved HTML implementation,
run by the native Node adapter. Original LPX3 supplies the closed-loop coded
excitation at 2/3/4 bits. Separately named LPX4 v1 extends that quantizer to
6/8 bits. The implementation and format are described in
[LPC2_EXCITATION.md](../../codec/LPC2_EXCITATION.md).

All comparisons use the same complete 7500 Hz inputs, source level, DC and
timing. Automatic brightness and output normalization are disabled. The
parametric LPC2 profile uses its original default postfilter 0.35; residual
profiles use the predictor coefficients without that synthetic-excitation
postfilter. This distinction matters: retained excitation, rather than the
postfilter, drives the waveform improvement in these results. The reference
web page's default 12000 Hz is not the rate used here.

## Four phrases

STOI/eSTOI pairs below are rounded. Bytes include the 24-byte outer header,
the entire LPC2 base, block scales and packed excitation. Code/runtime memory
is excluded.

| Recording | Current before | LPC2 only | LPX3 4 bit | LPX4 6 bit | LPX4 8 bit |
| --- | --- | --- | --- | --- | --- |
| Vinni, 2.970 s | .838/.645 | .619/.416; 537 B | .986/.976; 11994 B | .995/.992; 17562 B | .997/.995; 23130 B |
| Tail, bell plus full voice, 2.577 s | .705/.483 | .636/.397; 437 B | .952/.890; 10383 B | .986/.973; 15215 B | .992/.987; 20047 B |
| Chego, 1.229 s | .911/.857 | .595/.504; 321 B | .829/.802; 5076 B | .901/.903; 7380 B | .930/.933; 9684 B |
| Otvechaesh, 1.058 s | .841/.705 | .548/.339; 241 B | .780/.704; 4339 B | .919/.893; 6323 B | .955/.948; 8307 B |

Vinni/tail before files are the current exact Q3 renders. Chego/Otvechaesh
before files are numeric decodes of the SHA-verified public Tiny models.
They are not interchangeable with the generic corpus HQ4 initializer.
Per-profile source/PCM/container hashes and full spectral/raw measurements
are in [Vinni](vinni/report.json), [tail](tail/report.json),
[Chego](chego/report.json) and [Otvechaesh](otvechaesh/report.json).

The protected-recording guard compares each of Chego/Otvechaesh independently:
STOI/eSTOI must not decrease, and each of fine spectral error, envelope error,
unsupported energy and missing energy must not increase. A 1e-9 numerical
tolerance is used. Uniform 4-bit fails both protected recordings; 6-bit fails
Chego's STOI. Uniform **8-bit passes all six metrics for both recordings**.
[protected-regression.json](protected-regression.json) retains the decisions
and explicit old-baseline fallback selection for rejected profiles. A fallback
is not reported as a successful new candidate.

For these four phrases, 8-bit raw SNR is 30.69–35.47 dB and raw output/reference
RMS ratio is approximately .9985–.9994. Their 4/6/8-bit outputs have zero samples
at the final [-1, 1] endpoints. The tail 2-bit profile has one endpoint sample.
This does not establish absence of the reference decoder's internal limits.

## Twenty RU/EN short corpus recordings

The prepared manifest SHA-256 is
`4b6c7b7a039cba2794465e4b4c7412c5b7e49b60894b4132ae87615116cab982`.
The corpus includes four Russian and four English speakers, male/female,
tuning/evaluation splits, sixteen natural segments and four quiet/noisy
variants. Every tested segment is the complete prepared 2.048-second input.
All twenty completed, with a source-matched generic HQ4 before render in each
report. No failed case was omitted.

| Profile | Complete data bytes | STOI range | eSTOI range |
| --- | ---: | ---: | ---: |
| LPC2 Improved only | 101–444 | .2541–.7418 | .0258–.6022 |
| LPX3 2 bit | 4170–4513 | .7556–.9500 | .6492–.9086 |
| LPX3 3 bit | 6090–6433 | .8829–.9845 | .8032–.9720 |
| LPX3 4 bit | 8010–8353 | .9491–.9953 | .9035–.9923 |
| LPX4 6 bit | 11850–12193 | .9730–.9993 | .9656–.9988 |
| LPX4 8 bit | 15690–16033 | .9793–.9996 | .9710–.9995 |

Ranges describe the finite corpus; they are not a regression acceptance rule.
The complete per-recording results and group labels are in
[corpus-summary.json](corpus-summary.json), with full diagnostics under
[corpus-natural-a](corpus-natural-a/corpus-report.json) (eight natural `a`
segments) and [corpus-remaining](corpus-remaining/corpus-report.json)
(eight `b` segments and four stress variants).

For the two -24 dB inputs the 8-bit output/reference raw RMS ratios are .99960
and .99769. Their levels are preserved rather than boosted. Across all 100
corpus residual outputs there are zero final endpoint samples. Raw measurements
also retain source overshoots, including one sample above 1 in `ru_russia_b`.
The original decoder's output clamp prevents exact recovery of such a source.

Higher width is not an unlimited quality cure: `ru_slutskaya_b` remains the
weakest 8-bit case (STOI .97934, raw SNR 15.85 dB, RMS ratio .95698). Other
8-bit cases also plateau. This is an observed limitation of the reused scale
search/filter implementation, not an inferred guarantee about the cause.
The detailed files preserve those failures for the next controlled change.

The strict top-ten-partial **5 dB all-components requirement still fails on
all twenty recordings at every profile**, both raw-level and level-matched.
Missing selected peaks are violations; matched-only averages are not used to
claim success. High STOI therefore does not prove that this stricter target,
or perceptual identity with the original, has been reached.

## Validation and generated review files

Five focused tests cover original 2/3/4-bit byte identity, complete size/count
accounting, parameter-only roundtrip, descriptor/truncation/padding checks and
explicit quiet-source 6/8-bit behavior. The actual probes also decode using an
empty base-only cache, then the independently retained original JavaScript
decoder. All 120 residual containers across the four phrases and twenty corpus
recordings produce bit-identical Python/JavaScript float32 PCM. Reported source
hashes use normalized LF text; all corpus hashes and actual file sizes were
checked after the runs.

Generated, ignored files remain under `build/lpc2-quality/`:

- `vinni/`, `tail/`, `chego/`, `otvechaesh/` contain raw individual WAVs,
  complete containers and `comparison.wav`.
- `corpus-natural-a/<id>/` and `corpus-remaining/<id>/` contain the same outputs.
- `corpus-summary.json` and `protected-regression.json` mirror the retained
  JSON reports.

Listening sequences alone apply a labeled common highpass/global RMS match
and shared peak scale. Individual output WAVs and raw measurements preserve
the actual decoder output. No original/derived audio or binary experiment
containers are committed. Optional lossless entropy packing is a separate
experiment; its smaller byte counts must not be confused with raw LPX3/LPX4
sizes or with an AVR program/data budget.
