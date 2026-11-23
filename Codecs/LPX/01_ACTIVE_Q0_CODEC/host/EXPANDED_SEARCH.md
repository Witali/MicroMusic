# Optional pitch and gain refinement

`adaptiveEncode(..., expandedSearch=false, sizeAllowancePercent=0)` preserves
the independent Python adaptive reference by default. The existing
`enc_adaptive` WASM ABI selects that path. `enc_adaptive_extended` additionally
runs the shared C++ `refinePitchGain` operator after the reference stages.
Native PC, scalar WASM and SIMD WASM compile the same operator. No Python
runtime, external service, assembly or new decoder feature is required.

The extension whitens reference PCM with the stream's frozen LPC coefficients.
For each selected 160-sample block, normalized positive autocorrelation proposes
the three best periods in 18..145 and their immediate neighbors. The original
period and its ±1/±2 neighbors remain candidates. Integer synthesis evaluates
all eight representable pitch gains (0, 2, ..., 14), jointly with the current
scale and its immediate neighbors. The four best local candidates refit
excitation with the existing 160-sample lookahead. A parameter proposal uses a
320-sample loss horizon. At most 64 distributed/high-error 320-sample anchors
are examined per pass, for at most two passes.

Autocorrelation proposes candidates; it does not choose the output. Full
continuous-stream synthesis, PCM/PWM error and STOI, voice/noise score, clipping
and voiced-period diagnostics guard each complete candidate. The selected
reference-stage candidate stays in the pool. Candidates from both safe passes
remain available, and the shared C decoder verifies their entire packed V9
output including EOF. These are offline encoding operations; they make no new
AVR timing or interrupt-support claim.

With `maxBytes=0`, `sizeAllowancePercent` applies to the original complete v5
control size before lossless V9 repacking:
`floor(controlBytes * (100 + allowance) / 100)`. An explicit `maxBytes` overrides
that calculation. Supported allowance values are integer percentages 0..100;
the default is zero. This is a complete-file budget, including control/header
costs, rather than a per-block pulse quota. It can permit existing optional
extra pulses without changing sample rate, input level, recording continuity,
or producing multiple output files.

Reproduce the synthetic tail/silence/clipping/quiet/pause checks and the public
speech check with:

```text
build/python-reference/bin/python web-player/scripts/check-lpx-expanded.py --encoder build/lpx-native-encode --full
```

The native helper accepts `extended` instead of `adaptive`, followed by the
reference-stage call count and an optional allowance percentage. Each helper
run independently checks every decoded sample against the integer model.
Numerical improvements are candidate-selection evidence; listening comparisons
are still needed to establish audible benefit.
