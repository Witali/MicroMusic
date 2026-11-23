# Full-band spectral measurements and prospective admission

## Current magnitude/time multi-metric phase

The source spectrogram and its evolution, rather than bit-identical source
noise, are the current target. The original v1 measurements and strict gate
below remain reproducible. The new fields do not change their arithmetic.

For each frame/bin let `r[f,k] = abs(X[f,k]) - abs(Y[f,k])`. Starting with the
second frame, temporal residual is `r[f,k]-r[f-1,k]`. Sum its square with the
same one-sided weights and power normalization as magnitude error. There is no
extra transition from an invented zero spectrum before the first frame.

Balanced magnitude and temporal errors average their absolute band powers
divided by `max(sourceBandPower, totalSourcePower*1e-4)`, across every 1 kHz band.
For a silent source each denominator is one. Thus quiet upper bands remain in
the objective without an output-dependent mask or reference change.

Current safety requires valid source-rate STOI, source-period match counts,
collapsed-frame count and clipping not to worsen. Each PCM/PWM path also protects
total magnitude error, balanced magnitude error and balanced temporal error.
Selection combines frozen-incumbent-relative spectral/time/voice/noise/waveform/
STOI/period/shape losses with the weights in [PROFILE_QUALITY.md](PROFILE_QUALITY.md).
Waveform SSE and individual band retention are reported; they are not strict
sample-identity requirements. Tradeoffs remain visible in independent results.

This revised rule was specified on public tuning material before any new
wideband heldout codec outputs. It follows the user's clarified spectral/time
target. It does not establish an audible gain or a mathematical global optimum.

## Archived v1 conservative admission

This conservative rule was fixed before viewing heldout results on 2026-11-23.
It supplements the protected incumbent, full-rate PCM/PWM SSE and true-rate
STOI in the new quality phase. It does not replace the original 8 kHz evaluator.
There is no gain fitting, waveform alignment or reference-dependent EQ.

`FullBandContext(reference, sampleRate)` accepts 8000, 12000 or 16000 Hz.
`measure(candidate)` retains both native PCM and the production 8-bit PWM view.
Invalid rates, empty inputs and mismatched candidate lengths cannot pass.

- Use a native-rate 512-sample symmetric Hann window,
  `w[i] = .5 - .5*cos(2*pi*i/511)`, with hop 256.
- Frame starts are -256, 0, 256, ... while start < sample count. Samples outside
  the recording are zero. This includes leading and trailing single samples.
- Use real FFT bins 0 through 256. One-sided energy weights are 1 for DC and
  Nyquist and 2 otherwise. Bin k belongs to
  `min(floor(k*rate/(512*1000)), bandCount-1)`, with `bandCount=rate/2000`.
  Thus all bands are fixed 1 kHz intervals; the final band includes Nyquist.
- Sum source/output powers and squared magnitude residuals over every frame.
  Divide by `frameCount * 512 * sum(w*w)` for mean PCM16-unit power. Source
  support is frozen where band power is greater than 1e-4 of total source power.
  There is no absolute level cutoff, including for quiet sources.
- Per-band error is magnitude residual power divided by source band power when
  nonzero, otherwise by 1. Total error is summed magnitude residual power
  divided by total source power when nonzero, otherwise by 1. Silence therefore
  uses absolute mean PCM16-unit residual power.
- Per-band retention is `min(1, sqrt(outputPower/sourcePower))`, or zero for a
  source-empty band. Retention is capped so extra noise cannot earn a benefit.
- For both PCM and PWM, total error must not increase. In every supported band,
  normalized error must not increase and capped retention must not decrease.
  Each comparison has only an absolute 1e-12 floating-point tolerance.

An unsupported band is still included in total residual. A silent source has no
supported bands and still protects total residual. The context retains only
constant-sized analysis arrays; it recomputes source spectra when measuring
candidates rather than caching a recording-sized spectrogram.

This guard can reject useful tradeoffs and retain an incumbent. Acceptance is
an objective floor, not evidence of an audible quality improvement. Independent
corpus reporting uses the same admission view plus broader diagnostics.
