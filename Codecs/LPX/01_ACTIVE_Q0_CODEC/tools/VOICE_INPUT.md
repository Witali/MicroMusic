# One declared input gain before PCM16 rounding

The new voice CLI defaults to the user-selected `auto-quiet` policy. The library
`encode_speech_voice.encode` integer-input default remains `preserve`;
`adaptive_speech_voice.encode` defaults to `auto-quiet`. Both paths share
`voice_input.plan_level` and report the declared policy explicitly.
All level changes remain in the numeric report and returned `target.wav`.

WAV samples are read and, if necessary, resampled to 8 kHz mono in float64.
The whole input then receives one power-of-two gain before a single final
PCM16 rounding. This ordering matters: a valid FLOAT/24-bit source may be wholly
below half a PCM16 count. Rounding it first would erase information which was
still present in the source recording. Source silence and constant DC are not
amplified. Long inputs receive one plan before codec reset segmentation, so
relative dynamics are not independently normalized per segment.

Only AC RMS below 256 PCM16 units enables amplification. The gain aims for at
least 1024 RMS when the 29490-count peak bound permits it. Level analysis scales
before squaring to avoid variance underflow for quiet floating samples. The
gain is applied with `ldexp`; its integer exponent remains recorded even when
the abstract gain itself exceeds finite float range. A source that already
quantized to silence before the file was saved cannot be recovered here.

The input file is not modified. Reports retain original rate/channel/subtype,
the one declared gain/exponent, full output length and any clipping caused by
an already out-of-range input or resampling overshoot. Gain planning adds none
for amplified inputs because it checks peak headroom. This is a playback-level
transform chosen by the user, not a fitted metric gain.

An original v5 baseline still supplies its complete-byte cap. After a changed
input level it is not used as if it were a control at the new target level:
the encoder creates a fresh legacy target-level control. For gain 1, the old
control anchors the seed search. The MCU format, arithmetic and program are unchanged.

Checks cover float/24-bit tones which the former conversion rounds to zero,
exact integer target scaling, long-record dynamics, silence/DC, quiet-double
variance underflow, stereo/resampling and malformed input. These tests establish input handling,
not perceptual equivalence of the later lossy codec.
