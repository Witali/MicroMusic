# Bounded roughness and byte-budget probes

This is one user-targeted diagnostic after the user heard a large improvement
from V1 automatic quiet amplification, but still reported roughness relative to
the original. It is not independent held-out or corpus-wide quality evidence.
The seven-call matrix was declared before fitting. No new format, MCU source,
encoder default or V1 gate was changed.

Every candidate uses the same full 32,000-sample original multiplied exactly
by 64, with no clipping, trimming, resampling or fitted output gain. Input peak
is 19,584 PCM16 units; every decoded result stays below 90% full scale. The
observed roughness is not explained by gross signal clipping in these files.

## Fixed matrix and exact storage

[protocol.json](protocol.json) freezes the seven calls, existing helper settings
and complete output-byte caps. The selected V1 seed is profile 4 / pre8192 /
1,702 B. The captured pre13926 zero-enabled alternative is 1,698 B. The existing
profile-6 2,519 B stream is only a capacity reference, not a same-1,800-B result.

The extras syntax charges **800 marker bits / 100 B** before any active extra
pulse. The 1,702 B selected seed needs 1,802 B even for an empty forced marker
layer and **1,803 B for its first active extra**. Its exact capacities at
1,800 / 1,930 / 2,060 B are 0 / 103 / 207 extras. The alternative's first extra
fits exactly at 1,800 B. Headers, mandatory stored packets and final padding
are counted by actual serialization; the last available byte is not treated
as an independent impulse budget.

Extras use H320, six position candidates, batch16 and 128 full evaluations.
Expanded LPC uses the existing 64-frame / four-spectral-finalist / 1,280-sample
lookahead / 160-sample excitation horizon / two-pass preset. The chain starts
from the actual extras-1,930 result. The older enhancer API receives an exact
temporary v4 representation of each no-extra captured seed; v5 repacking must
recover the original bytes before fitting. Its cap always applies to the
actual final v5 output, not that auxiliary representation.

## Completed selected endpoints

Both gate columns below compare with the selected 1,702 B V1 seed. Metric gates
include PCM/PWM SSE and STOI; the voice gate is the frozen V1 PCM/PWM proxy
policy. Helper-internal selection is separate. Every endpoint remains an
experimental output here, not an automatic adoption or audibility claim.

| Endpoint | Cap | Actual B | Active extras | Within-tolerance PCM / PWM windows, source 77 | Voice objective | Metric / voice gates |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| V1 selected control | — | 1,702 | 0 | 58 / 57 | 0.18355 | control |
| Selected → extras | 1,800 | 1,702 | 0 | 58 / 57 | 0.18355 | pass / pass |
| Selected → extras | 1,930 | 1,913 | 89 | 63 / 63 | 0.17016 | pass / pass |
| Selected → extras | 2,060 | 1,913 | 89 | 63 / 63 | 0.17016 | pass / pass |
| Selected → expanded LPC | 1,800 | 1,705 | 0 | 62 / 60 | 0.17365 | pass / fail |
| Extras-1,930 → expanded LPC | 1,930 | 1,930 | 102 | 67 / 66 | 0.15739 | pass / fail |
| Pre13926 alternative → extras | 1,800 | 1,800 | 1 | 57 / 56 | 0.20447 | fail / fail |
| Pre13926 alternative → extras | 1,930 | 1,861 | 50 | 58 / 58 | 0.19603 | pass / fail |
| Existing profile-6 capacity reference | — | 2,519 | 0 | 69 / 69 | 0.13546 | larger reference |

The fully gate-preserving improved endpoint is 1,913 B, 211 B above the V1
selected stream. PCM/PWM error energies fall from 21.675 / 21.902 billion to
19.470 / 20.020 billion. These are numerical errors, not percentages of sound
quality. The 2,060 B extras call returns byte-identical output: both calls reach
the **128-full-evaluation bound**, with unused capacity. This is a search-bound
outcome, not evidence that more bits cannot help.

LPC at 1,800 B and the 1,930 B chain improve several proxies but remain explicit
tradeoffs. LPC raises PCM spectral-shape RMS from 5.8418 to 5.8691 dB and PWM
RMS from 8.4907 to 8.7588 dB; PWM collapsed-active frames rise from 3 to 4.
The chain's PCM gate passes, while its PWM collapsed-active count is 4 and
spectral RMS is 8.6619 dB, also failing the frozen voice gate. No gate was
relaxed to admit these outputs. Their helper raw and selected bytes happen
to be identical, and both roles are retained.

## Source-relative harmonic balance

An exploratory descriptor uses only the 77 source-confident 80-ms windows at
20-ms hops. A source-frozen sinusoid/cosine grid extends through 3,800 Hz;
sqrt-Hann weighted QR projection measures the fraction of energy outside that
grid. Candidate F0 tracking cannot remove a difficult window. The comparison
uses the **source's natural off-grid balance**, rather than seeking zero noise:
aspiration, modulation and source F0 estimation error can all contribute.
PWM is also compared with directly quantized source PWM on the same grid.
This is not calibrated HNR, roughness, or a subjective-quality score.

The source off-grid mean is 0.30138. Mean absolute per-window balance difference
is 0.05042 for the V1 selected PCM, 0.04593 after extras, 0.04543 after strict-cap
LPC and 0.03881 for the chain. The larger profile-6 reference is 0.02182. These
descriptors support further listening and controller evaluation; they are not
a replacement for the original content or the frozen gates.

## Validation and limits

[results.json](results.json) preserves all five captured baselines, all seven
selected endpoints, both LPC raw roles, negative/gate labels, actual layouts,
work limits, wall times and separate PCM/PWM/voice/harmonic descriptors.
There are 14 output bindings and 10 distinct serialized streams. Explicit final
checks give 56 native output-domain comparisons / 1,792,000 sample-domain
comparisons against the exact model. Reused/duplicate bindings are not claimed
as independent evidence. The timed helper region is 27.98 wall seconds, starting before native-session
initialization and baseline measurement, and including candidate diagnostics
and validation. Source feature preparation precedes that timer. This is not
pure search CPU time.

V1 core `5b4800f7` and decoder `5c7e0592` stay unchanged. Exact sources, runner,
input/handoff and prebuilt native library bytes were guarded before and after
every helper call and at completion. [source-runtime.json](source-runtime.json)
retains public source identities and provenance. The exact exploratory runner,
source protocol, media-derived hashes, original paths, streams and WAVs remain
in ignored storage. Exporting the anonymous evidence did not rerun fitting.

No complete linked AVR image, Flash/SRAM/stack observation, interrupt test or
board measurement was added for these endpoints. Data-byte savings/growth
must not be substituted for full firmware cost or timing admission. Unified
automatic selection and full-corpus verification are separate subsequent work.
