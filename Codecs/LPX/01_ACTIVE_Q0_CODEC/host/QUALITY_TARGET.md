# Selectable PCM and AVR PWM quality targets

The host encoder accepts an output-quality target independently of accuracy,
bitrate, arithmetic backend and input loudness normalization:

- `pwm` / `QualityTarget::Pwm` / `LPX_QUALITY_PWM=1` retains the existing
  objective: evaluate decoded PCM and the modeled AVR PWM transfer together.
- `pcm` / `QualityTarget::Pcm` / `LPX_QUALITY_PCM=0` evaluates decoded PCM only,
  suitable for computer playback, I2S and DAC output.

**The default remains `pwm`.** Existing C/C++ calls, JS options and browser
settings retain their previous behavior. Explicit unknown target values fail
validation. The option is a host search policy; V9/Long syntax, decoder
arithmetic, PWM hardware and downloaded player firmware do not change. Either
mode produces an ordinary LPX file supported by existing decoders. Choosing
PCM does not promise a smaller file or better quality on a PWM device.

## What PCM mode changes

PCM mode skips PWM conversion and its SSE, STOI, voice/noise, spectral,
temporal, retention and octave constraints during quality-aware selection.
It retains the PCM objective, complete-output verification, clipping/level
guards, interpolated predictor stability and complete-file byte budgets.
Local seed pulse search already uses PCM synthesis/SSE; its numerical kernel
is unchanged. The option affects quality-aware control, recovery, refinements
and final admission, including streaming continuation.

Quality and spectral measurements carry their target. Inactive floating-point
PWM fields are NaN and inactive integer error uses `UINT64_MAX`; these are
uncomputed values. Comparisons use the active path count and reject mixed
targets. Do not serialize an inactive sentinel as a measured PWM result.
Relative objectives from different targets are not directly comparable.

## Use the option

The browser converter provides **Оценка качества** with PCM and AVR PWM
choices. The setting is carried through short and streamed encoding, accuracy
and legacy bitrate modes, worker messages and ordinary/SIMD backends. An
explicit PCM request requires the updated WASM exports and fails visibly on
an obsolete module.

```js
const bytes = encode(pcm, 8000, 6, progress, {
  accuracy: true,
  qualityTarget: 'pcm'
});
```

The native file wrapper accepts the same target:

```sh
node web-player/scripts/encode-lpx-native.mjs input.wav output.lpx --quality-target pcm
node web-player/scripts/encode-lpx-native.mjs input.pcm output.lpx --pcm --quality-target pwm
```

Here `--pcm` describes raw PCM16 input; `--quality-target` selects the encoding
objective. The native executable reports `qualityTarget` in its JSON metadata.

```cpp
auto stream = lpx::encodeAccuracy(reference, 6, 8000, report, 4, nullptr,
                                  lpx::QualityTarget::Pcm);
```

Typed C++ encoder/context APIs append a target with the old PWM default. C ABI
functions with `_target` append an integer target; existing names are PWM
wrappers. For example, after reserving and filling input PCM:

```c
int bytes = enc_accuracy_target(samples, 6, 8000, 4, 0, -18, 12, LPX_QUALITY_PCM);
```

The other explicit entry points are `enc_adaptive_target`,
`enc_adaptive_extended_target`, `enc_adaptive_loudness_target`,
`enc_adaptive_level_target`, `enc_bitrate_target`, `enc_bitrate_loudness_target`,
`enc_bitrate_level_target`, `enc_stream_create_target` and
`enc_stream_create_accuracy_target`. The stepped seed-only API has no PWM
quality evaluator and keeps its existing PCM search semantics.

## Ownership and validation

The target belongs to a stream, evaluator or streaming session. A session's
choice is immutable, both carried histories retain it, and a candidate cache
rejects a stream with a different target. There is no global quality-target
setter. This does not make the existing default high-level C ABI concurrent;
its output/report ownership is unchanged. Independent native scoring tests
prewarm shared analysis tables before concurrent context checks.

Focused tests cover actual PCM/PWM preference crossings, PCM-only whole-output
admission, invalid values, mixed-target rejection, cache isolation, continued
streams, C/JS dispatch and default compatibility. The public corpus regression
compares default encoding byte for byte with all eight retained LPX baselines.
Generated test receipts and media remain in ignored `build/`.
