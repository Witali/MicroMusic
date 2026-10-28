# Explicit zero-step excitation candidates

`speech_v4.search(..., allow_zero_scale=True)` and
`speech_v4.encode(..., allow_zero_scale=True)` retain every legacy scale
candidate, then append the canonical first zero-step code and the first
positive-step code if not already present. The default remains `False`;
the WAV CLI exposes the explicit `--allow-zero-scale` switch.

The old residual-energy estimate has `desired >= 1`. On a zero residual this
places the scale-code center at 8 and searches only 6..10, which excludes every
zero-step alias. In profile 4, the mandatory +/-8 base pulse therefore injects
signal even for a silent source. Profile 6 can already choose amplitude 0 and
remain silent; its equal-cost legacy fields are retained by the old tie order.

The added candidates use the existing table and syntax. Their order follows
the legacy neighborhood, strict improvement remains required, and duplicate
codes are not evaluated again. At most seven scale codes are considered.
They are proposals, not a rule forcing low-energy frames to silence: the same
exact integer 160-sample block fit chooses among all candidates.

The encoded format, decoder and original PCM level/duration are unchanged.
For v5, the caller can repack the v4 result with `speech_compact.repack`.
True silence with the option is exactly zero in the model and both native
layouts, including partial stored-packet tails. Prechange synthetic normal
bytes remain identical with the default and with the explicit false setting.

This fixes a missing candidate. It does not prove that pitch survives low
signal levels, avoid PCM16 quantization limits, or overcome a neutral 8-bit PWM
output for sub-LSB signals. Full-record criteria, old quality gates, actual
serialized size and target timing still require separate checks.
