# v5-only development: smaller firmware and better encoding

The primary embedded speech target is now the explicit v5-only build. The
same-format decoder saves **300 program bytes** on all eight fixed speech
images. Two new offline refiners improve existing v5 data without new decoder
modes. The same-byte pipeline improves 93/98 speech case/profile pairs; larger
budgets remain optional choices for listening, with actual-byte tradeoffs kept.

Baseline: `1ae4aa99` (decoder arithmetic from `3680f86c`). No v5 syntax, public
API, arithmetic-backend selection or general-library defaults were changed.

## Firmware result

ATmega328P / AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0, simavr 1.6, 16 MHz CPU /
8 kHz audio, queue 512 / prefill 384, LPC segments 2, explicit ASM. Same recipe:
`-Os -flto -mcall-prologues -mrelax`, unroll 1 / tuning 0. v5-only additionally
sets `LPX4_ENABLE_SPEECH=1`, `LPX4_ENABLE_SPEECH_COMPACT=1`,
`LPX4_COMPACT_ONLY=1`. Apply the same flags to all consumers.

| Build | Program Flash before | After | Saving | Static SRAM |
| --- | ---: | ---: | ---: | ---: |
| v5-only, eight unchanged streams | 5363-5364 B | **5063-5064 B** | 300 B / 5.59% | 1085 B, unchanged |
| Common, same streams | 7225-7320 B | 7083-7178 B | 142 B | 1105 B, unchanged |

Program Flash is `.text + .data` minus the exact embedded compressed stream;
startup, runtime, tables and retained profiling/playback harness are included.
This is neither ELF file size nor an isolated library footprint.

Mean decode wall cycles/sample, including IRQ and instrumentation, change from
804.737145 to 800.998199 (-0.46%) in v5-only, and 872.820309 to 888.795691
(+1.83%) in common. Useful PWM is exact. Normal and +100-cycle IRQ continuous
controls pass in both ASM layouts. The portable C fallback remains output-exact
but misses the 8 kHz deadline on this AVR recipe. These are specified simulator
workloads; no physical board or universal worst-case support is claimed.

The implementation compresses the exact cosine table into checkpoints, slopes
and packed second differences, specializes compact scale lookup, simplifies
bounded Rice arithmetic, and removes a proven redundant compact pitch clamp.
No assembly was added. [Technique and constraints](../../../../docs/avr-asm-cookbook/lpx-program-flash.md#exact-v5-only-tables-and-bounded-arithmetic-2026-10-27).
[Decoder measurements and hashes](decoder-measurements.json).

## Corpus and evaluation

The canonical cache has 181 cases / 306 segments / 15,188,029 samples
(1898.504 seconds): 49 speech cases with 59 segments / 329.037 seconds, and
132 non-speech cases. These include related levels, conditions and prepared
material; they are not 181 independent speakers or a held-out listening study.
Original external source media were not reimported in this run. Canonical PCM,
reference joins, signed cache reports and artifact hashes were verified.

All 1224 retained baseline/selected v5 streams match frozen PCM/PWM and the
independent model in both final native layouts. Every comparison preserves
original levels and complete joins; no fitted gain, delay or trimmed scoring.

Two new encoder-only tools:

- `refine_speech_compact.py` caches the unclipped LPC signal and searches
  existing header filters: 256 proposals, up to 16 full-metric candidates.
  Spectrum and excitation remain exact; complete stream size is unchanged.
- `refine_speech_excitation.py` jointly probes existing scale/pitch/base/extra
  pulse fields. Spectrum and header filters stay fixed. One pass, 160-sample
  horizon, 1280-sample groups; exact complete-stream caps include markers and
  padded-tail extras. Existing integer synthesis is reused.

The input stays eligible. Selected results preserve full-reference PCM/PWM SSE
and available PCM/PWM STOI (numerical tolerance 1e-12); complete joined recordings
are checked again and can roll back. Short or insufficiently active STOI is
reported unavailable; a genuine score of 1e-5 is not discarded by value.
Spectral error remains a separate diagnostic and sometimes worsens despite
these four floors. None of these metrics is a percent of perceived quality.

## Speech result

The header stage selects 63/98 improvements at unchanged bytes. Joint search
then evaluates all 49 cases in both profiles and two budgets: 196 joined
variants / 236 segment fits. The complete header+joint pipeline improves 93/98
pairs at the existing size, or 97/98 under the larger caps.

The table compares the final pipeline with the original strongest retained v5,
not only the intermediate header result. SER gain uses total error energies;
STOI gain is the unweighted case mean across all 49 cases.

| Profile | Budget | Actual stream growth | PCM SSE reduction | Aggregate PCM SER gain | Mean PCM STOI gain |
| --- | --- | ---: | ---: | ---: | ---: |
| 4 | Existing bytes | 0% | 5.75% | +0.2574 dB | +0.001623 |
| 6 | Existing bytes | 0% | 6.59% | +0.2961 dB | +0.001493 |
| 4 | Nominal +10% cap | +9.47% | 9.53% | +0.4351 dB | +0.002405 |
| 6 | Nominal +10% cap | +8.96% | 9.47% | +0.4319 dB | +0.002549 |

Existing aggregate stream bytes are 150962 / 216081 for profiles 4/6; the
larger variants use 165265 / 235441. These corpus totals are not one firmware
image. Program cost is shared once per image, rather than subtracted per clip.
The pilot cap uses `ceil(binary_float(bytes * 1.10))`, which can permit one
additional byte at decimal boundaries. Exact configured caps and achieved
bytes are retained. The public refiner takes an exact integer byte cap.

The same-byte result is the conservative starting point. Four larger selected
points are dominated on the declared metrics and actual bytes: three by a
same-byte choice and one by its own joined raw branch. Keep the raw branch
for review: a conservative per-segment gate can reject changes that improve
the whole recording. The saved raw alternative is the best encountered
PCM-SSE proposal along the accepted trajectory, not a global or independently
optimized unconstrained result. Do not select the largest cap automatically.

A fair existing-enhancer control repeats the diverse 12-case pilot: 48 points,
identical header starts, references, reset geometry and complete segment caps.
The old enhancer rebuilds extras from the frozen v4-compatible base, with the
selected enhanced v5 kept eligible as rollback. It accepts 7 points; joint
selection is no worse in all four quality metrics in 44 points, mixed in 3,
and tied in 1. Including bytes, joint strictly dominates old selection in
21/48 points; reverse domination is zero. This is a bounded control, not a
claim against every possible equal-budget encoder search or a listening win.

[Full speech variants and controls](speech-results.csv) retain 782 anonymous
rows, including raw alternatives. [Protocol, sources, aggregates and Pareto
review](quality-summary.json) record limitations explicitly.

## A useful small-growth listening example

On one prepared 1.42-second clip, larger v5 streams gain PCM STOI by about
0.01493 / 0.01399 for profiles 4/6. These are individual short-clip results,
not evidence of a general audible gain. Full before/after AVR images were
measured with the old program/old audio and new program/new audio:

| Profile | Audio bytes | Total Flash | Total saving |
| --- | ---: | ---: | ---: |
| 4 | 739 to 813 (+74) | 6102 to 5876 B | 226 B |
| 6 | 1084 to 1134 (+50) | 6448 to 6198 B | 250 B |

Thus extra audio bytes can be worthwhile while the complete firmware becomes
smaller. These two outputs are retained for local randomized A/B/C listening
against original v5 and the same-byte result, using the same fixed PWM transfer.
The private audio and listening key stay ignored. No listener ratings have been
collected; naturalness, consonants and artifacts still require listening.

Eight distinct new streams, selected for dense extras, long segments, quiet and
noisy conditions, pass normal and +100 IRQ tests (16 images), with exact useful
PWM. Four further complete images measure the short before/after example.
[New-audio timing and total Flash evidence](new-audio-measurements.json).

## Non-speech robustness and validation

A smaller header-only search on all 132 non-speech cases (64 proposals / 2
full-metric candidates) selects 82/264 numerical improvements at unchanged
bytes. STOI is only a numerical diagnostic here, not music intelligibility.
[All branches](non-speech-results.csv) and [independent checks](non-speech-summary.json)
retain that distinction. No joint music-quality optimization is claimed.

Independent audits check 354 header, 708 joint and 1482 non-speech generated
stream instances, including duplicate rollbacks/raw branches: both receivers,
integer model, saved PCM/PWM, joins, caps and decisions match. Joint checks
also cover 5616 recorded segment checkpoints. Separate verification includes:

- 47 focused decoder tests before and after; exact scale/cosine checks in both
  layouts and the frozen 34816-conversion LPC fingerprint.
- 31 encoder/metric test executions, including short STOI, saturation,
  bounded rollback and changed partial tails with stored extras. Independent
  review additionally exercised 30 randomized arithmetic cases and three
  hard-link output-path collision checks.
- ASan/UBSan: 605670 mutation/reset cases per layout, exact resets and zero
  sample-cap exhaustion.
- 28 current-code AVR checks on the unchanged workloads, in addition to the
  new-audio and before/after comparisons above.

Private source names, paths, manifests, WAVs, payloads, ELF/HEX and listening
material are excluded from Git. Public labels are numbered independently.

## Use and reproduce

Use existing Python requirements and native compiler setup. Follow
[the v5 refiner workflow](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_COMPACT.md#further-v5-only-encoding)
and [the explicit embedded build recipe](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_FLASH.md).
Run `python -m unittest test_refine_speech_compact test_refine_speech_excitation`
with the active tools/tests on `PYTHONPATH`. Run the existing
`benchmark_speech_flash.py verify` with the small-code recipe and
`--compact-only`, plus `verify_fuzz.py --speech --speech-compact --compact-only`
for the corresponding sanitizer layout.

The full corpus run also needs the private canonical manifest and retained
selected v5 caches. Exact hashes, settings and all retained numerical branches
are in the linked reports. The portable C path and full common-format build
remain selectable; experimental LPWB period dictionaries are not part of v5.
