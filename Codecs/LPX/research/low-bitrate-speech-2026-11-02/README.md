# LPX speech at complete 2/3 kbit/s caps

The initial frozen search is complete: all 27 existing four-second clips at
both caps pass the independent model and common/v5-only native C checks.
All 54 selected complete ATmega328P players also pass active-IRQ exact PWM
validation with no underruns. Follow-up quality rounds are recorded separately;
these numbers describe round 0, not later changed streams.

## Initial speech results

The reference is the uniform spectral-hold control generated at the same
complete-file cap. The new search allocates spectral updates adaptively,
expands source/residual lag proposals, tries the legal gains and retains
clipping-aware closed-loop alternatives. A protected complete control remains
available under the unchanged PCM/PWM SSE/STOI/pitch/clipping guards.

| Heldout speech: 10 full clips | 2 kbit/s control → selected | 3 kbit/s control → selected |
|---|---:|---:|
| Mean PWM STOI | .69642 → .70727 | .61194 → .73292 |
| Aggregate PWM SER, dB | 3.4833 → 3.9307 | 4.0895 → 6.3500 |
| Source-period tolerance coverage | 30.98% → 44.44% | 25.43% → 56.62% |
| Hard-clipped samples | 1 → 0 | 0 → 0 |

Across all 20 speech clips, 17 selected streams change at 2k and 20 at 3k.
These are numerical diagnostics, not percentages of perceived quality or
proof of fully preserved pitch. The public 2.4-second phrase was used for
tuning and is excluded from these heldout aggregates. Existing higher-rate
streams are not interchangeable same-cap controls.

Seven acoustic-music/synthetic negative controls remain poor overall,
including substantial clipping and aggregate SER around −11 dB. This study
does not establish a useful general music/audio profile. The original source
noise remains part of the target; no output gain fitting or alignment is used.
Auto-quiet applies one declared source gain identically to all compared
candidates, before final PCM16 rounding.

## Scope and reproduction

See the prospective [initial protocol](PROTOCOL.md), all anonymous
[per-case measurements](initial-corpus.json), [group aggregates](initial-summary.json),
and [complete firmware costs/IRQ validation](FIRMWARE.md). The exact byte cap
counts headers, spectra, metadata, innovations, full terminal packets and
padding. Sparse80 uses explicit version 8/mode 15 at 2k;3k uses ordinary v5/P4.
No 1.5k preset is part of this search.

The active CLI is `tools/encode_low_bitrate_speech.py` in the adjacent codec.
`run_corpus.py prepare/work/export` provides fresh four-worker reproduction;
it refuses incomplete or merely claimed jobs. Use a fresh ignored output
directory and the established external 27-case corpus manifest. No original
or generated private audio, source identities, paths or fingerprints are
included here. The real common/v5-only receivers are rebuilt from the codec.

The initial version retained work counters associated with unique output
streams. Duplicate-output fits could therefore be omitted from their sum;
the numeric evidence explicitly labels that scope, while encoding wall times
remain the actually measured values. `audit_work.py` provides a separate
bookkeeping-only reconstruction without pulse refits. The current active
encoder records every attempt, verifies duplicate expected PCM and preserves
an atomic best pointer to immutable candidate bytes/metrics.

Listening export uses explicit integer PCM16 units and verifies reopened
samples. An earlier int32-to-PCM16 SoundFile call nearly silenced local WAVs;
it did not affect model/native metrics or encoded streams. The CLI now uses
the tested `pcm16_wav.py` writer.

The completed [iteration/stopping protocol](ITERATION_PROTOCOL.md) starts
from these selected whole streams, with separate source-pitch, spectral and
beam operators. A small numerical movement alone does not reset its
three-completed-no-clear-round counter. Decoder-cost experiments are isolated
from that frozen same-format campaign and need their own measured benefit.

All three follow-up rounds completed without a clear registered gain; their
smaller admitted improvements remain selected. See [the final quality results](CAMPAIGN_RESULTS.md)
and [54/54 complete final firmware admissions](CAMPAIGN_FINAL_FIRMWARE.md).
Those final images use the existing decoder, not the rejected metadata320 or
scale-ramp prototypes. No additional decoder complexity is adopted merely
because it fits a 10–20% allowance.

Separate bounded pilots tried shared metadata, a 49-point existing-header grid
at each budget, and raw-scale interpolation. None passed all protected quality
guards. The ramp cost only +0.27% / +2.26% producer work, but added 316 / 422 B
of program Flash and 4 B SRAM without an admitted corpus benefit. Some tuning
proxies improved while other guards worsened; these rejections do not prove
that every possible encoder for the experimental formats must lose.
[Measured costs and the external AVR observation method](../../../../docs/avr-asm-cookbook/lpx-producer-budget.md)
remain available, with the runnable prototypes preserved separately.

The measured campaign used encoder source at commit `9b83ac21`, with its
complete pinned research source archived privately. Subsequent correctness
fixes retain feasible seeds after individual spectral-proposal failures and
exclude unplayed packet padding from excitation fitting. Eight exact aligned
before/after comparisons preserve all parameters, pulses, PCM and fit counts;
the full corpus and listening clips here are aligned and remain unchanged.
Eleven low-rate contracts, two WAV-export tests and seventeen research tests
pass on the final branch. These are correctness checks, not new quality rounds.
