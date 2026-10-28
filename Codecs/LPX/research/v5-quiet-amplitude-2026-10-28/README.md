# Quiet source precision and fixed PWM are separate problems

All **16 predeclared cases complete**, with the original 8,000 samples and
gain retained. Every quantized source still has 47 candidate-period windows
near its known 200 Hz fundamental. At the three lower levels, fresh encoding
usually loses that observed periodic structure **before PWM**. The same quiet
sources themselves also disappear in the fixed 8-bit PWM transfer. Increasing
output noise until it crosses a PWM step is not preservation of the source.

[PROTOCOL.md](PROTOCOL.md) was committed as `73e7dd1a` before execution, followed
by the exact runner `928b2241`. The analytic source combines 200/400/600 Hz
harmonics with weights .7/.2/.1. Nominal scales 1/4/32/1024 produce actual integer
peaks **1/3/25/806** after a single round. Each is crossed with profiles 4/6 and
preQ14 0/13926. No refine, new objective, extra pulse, threshold tuning, input
normalization or case replacement was used. These are harmonic stress tones,
not original-corpus speech, speaker/voice-gender tests or perceived-quality data.

The table reports paired decoded/source candidate-period counts on the same
source-supported windows. They are estimator observations, not validated
true-F0 or independent time samples. A missing decoded period remains a failure,
not a favorable null cents score. Every source has 47 candidates.

| Actual source peak | Profile | preQ14 | Native PCM paired periods | PCM RMS | PWM paired periods | Non-neutral PWM samples | Complete v5 bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 0 | 0/47 | 17.91 | 0/47 | 0 | 373 |
| 1 | 4 | 13926 | 0/47 | 13.56 | 0/47 | 0 | 373 |
| 1 | 6 | 0 | 0/47 | 0 | 0/47 | 0 | 549 |
| 1 | 6 | 13926 | 0/47 | 0 | 0/47 | 0 | 549 |
| 3 | 4 | 0 | 0/47 | 20.05 | 0/47 | 18 | 373 |
| 3 | 4 | 13926 | 0/47 | 41.18 | 0/47 | 184 | 374 |
| 3 | 6 | 0 | 0/47 | 13.10 | 0/47 | 0 | 549 |
| 3 | 6 | 13926 | 0/47 | 21.44 | 0/47 | 78 | 555 |
| 25 | 4 | 0 | 0/47 | 33.37 | 0/47 | 83 | 373 |
| 25 | 4 | 13926 | 0/47 | 132.11 | 0/47 | 1303 | 373 |
| 25 | 6 | 0 | 40/47 | 23.53 | 0/47 | 20 | 555 |
| 25 | 6 | 13926 | 0/47 | 75.45 | 0/47 | 368 | 555 |
| 806 | 4 | 0 | 47/47 | 528.08 | 47/47 | 7214 | 373 |
| 806 | 4 | 13926 | 17/47 | 665.00 | 12/47 | 7061 | 376 |
| 806 | 6 | 0 | 47/47 | 531.64 | 47/47 | 7207 | 549 |
| 806 | 6 | 13926 | 45/47 | 612.05 | 45/47 | 7244 | 555 |

The peak-25/profile-6/pre-0 case retains 40/47 PCM periods, with fixed-source
period error 0.08271; pre 13926 retains none and has error 0.48519. At peak 806,
pre 0 retains every candidate period in both profiles; pre 13926 degrades the
profile-4 result especially. These outcomes identify useful follow-up questions
about existing analysis/search and header filters. They do not establish a
globally optimal pre value or authorize changing defaults.

Profile 4 stores only -8/+8 base innovations. At the three low source scales,
every emitted tuple uses Q14 step 2, while profile 6 uses step 1 and all-zero
innovations at peak 1, and generally step 2 at peaks 3/25. The source models
and syntax permit smaller/zero scale steps; the measured step 2 is a decision
of this unchanged fresh search, **not an inherent format minimum**. The two
profiles also differ in spectra and position coding. This matrix does not
isolate the compulsory innovation amplitude as the sole cause.

At source peak 1, native PCM16's even-valued output puts a source sample +/-1
equally far in SSE from 0 and +/-2 of the same sign. That arithmetic tie helps
explain why a strict waveform-error ranking can prefer silence without testing
period preservation. It does not prove that a better periodic complete stream
exists under every original budget and floor. The new voice-aware search is
outside this frozen experiment.

For all sources with peaks 1/3/25, the direct fixed PWM conversion has exactly
zero non-neutral samples; the native source information remains detectable in
PCM16 but is absent from that direct PWM representation. At peak 806 the
source has 7,200 non-neutral PWM samples. An encoder-only PCM improvement and
the fixed PWM resolution limitation must therefore be measured separately.

## Validation and reproduction

[summary.json](summary.json) is an exact copy of the complete anonymous run:
all cases, metrics, stored parameter/innovation histograms, actual bytes,
source/runtime pins and failures/no-fit state are retained. Runtime was 19.70 s.
There were no dropped, quantized-source-unassessed or no-fit cases. No byte or
full-Flash application admission was attempted.

All V4/V5/common/v5-only outputs match both integer models at every sample;
V4-to-V5 repack is lossless relative to decoded output. The runner checks six
native output domains per case. The fresh-process
[auditor](reproduction/audit_synthetic.py) reopened the exact source formula,
WAVs, encoded streams, model outputs, native libraries and metrics, and passed
**96 additional readback domain comparisons** over the same 16 signals.
[audit.json](audit.json) binds that executed auditor. The repeated verification
does not make 32 independent cases. Neither stage builds AVR firmware or
establishes IRQ timing, analog behavior or a new encoder default.

Retain the recorded source/runtime epoch to reproduce this baseline. A fresh
run after an encoder change is a new measurement, not an exact replay. From
the repository root, with the project Python packages and a native C++ compiler
available, use a fresh owned ignored output directory:

```text
python Codecs/LPX/research/v5-quiet-amplitude-2026-10-28/reproduction/run_synthetic.py build/quiet-amplitude-replay
python Codecs/LPX/research/v5-quiet-amplitude-2026-10-28/reproduction/audit_synthetic.py build/quiet-amplitude-replay
```

Do not use Python optimization flags; assertions guard the source/output
epochs. The runner sets numeric threads to one and rejects source changes.
Input/output audio, native library identities, media/PCM/stream hashes
and private receipts remain only in ignored build storage. No MIDI is used.
