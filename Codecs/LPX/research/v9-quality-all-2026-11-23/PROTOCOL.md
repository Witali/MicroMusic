# Prospective V9 encoder quality study

This study evaluates encoder changes against the exact `f282950c` incumbent. It
does not change the V9 decoder, its arithmetic or the meaning of a profile.
Freeze source, complete targets, this protocol and evaluator before measuring a
candidate. Private inputs, provenance, hashes, decoded media and detailed job
records stay under ignored `build/`; only anonymous numeric evidence is exported.

## Primary matrix

Use all 27 established four-second cases: 10 tuning speech, 10 held-out speech
and seven music/synthetic controls. These are case groups, not independent
speaker counts. The held-out cases must not be used to tune search constants.
The prospective ordinal split is tuning 0–3, 8–11, 16, 19; held-out 4–7, 12–15,
17, 18; controls 20–26. No case may be replaced after seeing its result.

Each case has eight settings: adaptive P4 and P6 at 8, 12 and 16 kHz, and strict
3 and 8 kbit/s complete-file budgets at 8 kHz. This is 216 jobs per encoder.
The original 8 kHz target is resampled once with SciPy's rational polyphase
resampler, then rounded and saturated to PCM16. Both encoders receive the same
prepared bytes and exact sample count. There is no fitted gain, alignment,
trimming or per-output reference change. Preserve-level is the primary setting.

The P4/P6 budget is the frozen incumbent control's complete v5 representation
size; pass that same explicit budget to both encoders. Its conservative V9
ceiling subtracts the removed header bytes (nine ordinary, five Long). Report
actual complete V9 bytes as well: a ceiling is not proof of equal actual rates.
The strict presets use `floor(samples * kbps * 1000 / (8 * sample_rate))` for
the entire V9 file. Search calls are four and size allowance is zero throughout.
The exact incumbent output remains available as a candidate.

## Pilot and separate audits

Before the primary run, evaluate three complete public phrases at all eight
settings (24 jobs), with one numerical worker. Inspect runtime and useful
candidate evidence before authorizing the larger run. Total concurrent
numerical workers across the team must not exceed three.

Optional level preparation is a separate ancillary matrix, initially four
cases by four 8 kHz settings (16 jobs). It remains on hold while decoded-output
constant file gain and its V9 metadata extension are being validated. Do not
mix results from the prior source-normalization implementation with that mode.

The archived Sparse80/2 kbit/s stream is a separate 27-case incumbent audit,
using each stream's original declared prepared target and exact expected
PCM/PWM. Lossless V9 repacking and decoder equality are checked separately.
This does not imply that Sparse80 is covered by the P4/P6 quality improvement.
One existing full Long speech excerpt is also tested separately with P4/P6;
never emulate Long by resetting independent short files.

## Independent measurements and admission

Every stream must decode completely with the production C++ V9 decoder into
both PCM16 and PWM. Require exact rate, exact sample count, clean termination
and the fixed gain130/round1 PCM-to-PWM transfer. Do not accept a container
header or the encoder's internal score as proof of decoder correctness.

Evaluate external `pystoi` at the actual 8/12/16 kHz rate on complete usable
clips. An insufficient-active-frames result is missing, not a score of 1e-5.
Keep baseline-assessable membership fixed; newly missing candidate scores are
failures. Music/synthetic controls do not receive a speech-intelligibility
score. Record PCM16 and fixed-PWM squared error, clipping and source-frozen
period diagnostics (80 ms windows, 20 ms hop, 50–800 Hz). The period estimator
is a diagnostic, not a true-F0 label or perceptual quality model.

Record raw candidate results even if a gate fails. A strict admission requires
no PCM/PWM SSE increase, no valid speech STOI decrease (numerical tolerance
1e-10), no lost source-period matches within 100 cents, no new clipping, and
the same complete budget and duration. Do not turn a rejected candidate into a
reported improvement by silently substituting the incumbent. Aggregate energy
by summation, preserve fixed STOI and source-period denominators, and separate
tuning, held-out speech and controls. Do not average dB or present objective
metric changes as perceived-quality percentages. Listening is still needed
before claiming a noticeable audible improvement.

Full-band analysis is performed independently at the actual native rate, up to
the 4/6/8 kHz Nyquist limit. Use fixed 1 kHz physical bands, a 512-sample
symmetric Hann window, hop 256, starts -256, 0, 256, ... below the sample count,
and zero padding outside the complete source. Assign FFT bin k to
`min(floor(k*rate/(512*1000)), band_count-1)` and use one-sided weights one at
DC/Nyquist and two elsewhere. Divide summed spectral power by
`frames*512*sum(window^2)` to report mean PCM16 power. Every band is reported,
including quiet/unsupported bands, with source/output power, complex residual,
squared magnitude residual and output/source energy retention when defined.

The separately reported spectral admission floor is fixed before held-out
evaluation. A band is supported when total source power is positive and its
power is strictly above 1e-4 of that total. Both PCM/PWM total squared-magnitude
residuals, normalized by total source power (or one for a zero source), must
not increase. Every supported band's residual normalized by its source power
must not increase, and `min(1,sqrt(output/source power))` must not decrease.
Use only an absolute 1e-12 comparison tolerance on these normalized values.
Keep unsupported-band output and residual powers in evidence; support is not
permission to hide added high-frequency noise. The primary cohort's originals
are genuinely 8 kHz. Its 12/16 kHz resampling can assess artifacts above 4 kHz,
but only a separate genuinely wideband source can test retained source highs.

## Harness interface

`corpus.py freeze` archives and builds the exact baseline from Git, never the
changing working source. `prepare` freezes one target set; `run` calls the
native driver and independent evaluator; `export` produces an anonymous
allowlisted summary. Paths in these commands should point into ignored
`build/`. See `--help` for arguments. A completed job receipt is written only
after native decoding, independent metrics and private artifact hashes succeed.

The native driver reads PCM16LE from stdin and writes one complete LPX stream
to stdout. `encode MODE RATE CALLS CAP PCM_OUT PWM_OUT` supports `p4`, `p6`,
`k3`, `k8`; CAP=0 derives the incumbent control budget for P4/P6. A candidate
run must supply the frozen baseline CAP explicitly. `decode PCM_OUT PWM_OUT`
audits an existing stream. Stderr contains one numeric JSON report. Python
orchestrates and evaluates; it is not a runtime LPX encoder implementation.
