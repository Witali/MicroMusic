# Quiet/voice encoder

The CLI defaults to the [unified adaptive search](ADAPTIVE_SPEECH_VOICE.md).
The seed-only procedure below remains available with `--search-mode grid` and
through this module's `encode` library function; adaptive orchestration lives
in `adaptive_speech_voice.encode` and reuses all of these verified seeds.

`encode_speech_voice.py` constructs complete v5 candidates with consistent
LPC reanalysis at preQ14 0, 8192 and 13926. Its candidates enable the bounded
zero-scale search option. The old default encoder remains a control. Existing
MCU code and v5 syntax are unchanged.

The source-frozen [voice objective](SPEECH_VOICE_OBJECTIVE.md) ranks candidates.
Conservative selection additionally requires the old complete PCM/PWM SSE/STOI
floors and nonregression of the measured voice-period coverage, fixed-period
difference, coarse spectral shape and collapse count in **both native PCM16 and
fixed PWM**. The report also measures direct PWM rounding of the source target,
so loss already caused by the output resolution stays visible. These are numeric proxies;
selection never establishes perceptual equivalence or reliable F0 in missing
windows. A uniformly lower pre-emphasis is not imposed on every recording.

All serialized headers, excitation, extras and padding count in `--max-bytes`.
With a supplied v5 baseline, its actual size is the default cap; otherwise the
fresh legacy control's actual size is used. A failed finite candidate grid is
reported as no fit, not an encoding-impossibility claim. Raw best-objective
alternatives remain separate from conservative output and retain their floors.
Output names must be fresh so no-fit cannot expose stale audio as a result.

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py reference.wav build/voice-result --baseline old.l4hy --profile 4 --max-bytes 1800
```

The reference is read/resampled in float and receives its declared whole-input
gain before final PCM16 rounding, so quiet FLOAT/24-bit input is not erased
before amplification. [Input handling](VOICE_INPUT.md). One invocation handles
1..64000 samples. Long recordings require their actual reset segments and a
separate whole-chain cap/metric check; per-segment caps are not a substitute.
For non-speech `--non-speech` skips STOI; periodicity/shape are still descriptive
proxies and do not establish music quality. Native common/model checks run for
every candidate; the CLI also checks the independent compact-only native layout.
Generated streams, WAVs and detailed reports belong in local ignored `build/`.

## Playback level is an explicit choice

`--level-policy preserve` keeps the original PCM level and length.
An 8-bit output can collapse a very quiet source even when its PCM16 pitch is
detectable. Source quantization, synthesis precision and PWM rounding are
reported as separate limits; preserving arbitrary sub-step detail is not promised.

The user-selected CLI default `--level-policy auto-quiet` raises playback level. It
uses one power-of-two gain for this entire input, only below 256-count AC RMS,
aiming for at least 1024 RMS when a 29490-count peak bound allows it. Silence
and constant DC receive no gain; loud inputs retain gain 1. No output gain is
fitted, no sample is trimmed, and multiplication is checked not to clip.
For gain !=1, the legacy control is freshly encoded at the **declared new
target level**; it is not mislabeled as an original-level metric comparison.
Report fields state gain, dB and that playback level changed. This default
follows the explicit user choice. It does not recover detail already lost in
the source PCM, and a long segmented chain must use one agreed whole-record
gain rather than independently amplifying segments.

The intended use is bounded encoder tuning plus explicit listening, followed by
actual complete-player Flash/SRAM/IRQ admission for selected streams. A data-only
fit or unchanged MCU source alone does not establish real-time support.
