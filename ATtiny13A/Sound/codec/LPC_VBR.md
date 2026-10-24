# LPV1: adaptive residual precision in the output domain

LPV1 is a separate PC research format. It embeds an unchanged LPC2 base and
codes the actual residual with 2, 3, 4, 6 or 8 bits per sample, chosen per block.
It is not LPX3, not AVR firmware, and is not lossless compression of an existing
LPX3/LPX4 file. It needs original audio when encoding; decoding needs only the
complete LPV1 container and the base-byte LPC2 coefficient provider.

## Causal quantizer and rate selection

Each candidate starts with the actual carried predictor history and previous
decoded output. For every sample, with predictor sum `p` and de-emphasis `a`:

```
desired_pre = original_sample - a * previous_actual_output
q = round((desired_pre + p) / step), bounded to the signed width
decoded_pre = q * step - p
decoded_output = decoded_pre + a * previous_actual_output
```

The predictor history receives `decoded_pre`; de-emphasis receives the actual
decoded output. This happens on every sample, not just at block boundaries.
There are no state resets, crossfades or concatenated independent streams.
The unchanged original LPX3 decoder kernel is used for the trials and final
parameter-only decoding. The new causal encoder preserves its predictor,
rounding rule, signed-code range and defensive emphasized-state guard.

Each 75-sample block tries ascending widths and 13 scale ratios:
`.30,.45,.60,.75,.90,1,1.12,1.30,1.55,1.85,2.25,2.90,3.80`.
Duplicate encoded scale bytes are tested once. The nominal step uses the
original inverse-filtered residual RMS. Within a width, the lowest raw decoded
output MSE is chosen. The first width meeting the block target is accepted.
The target is MSE <= `max(original_block_power, global_floor_power)` times
`10**(-target_snr_db/10)`. The default global floor is 60 dB below whole-file
reference RMS; its exact value and affected blocks are reported.

If the finite grid cannot meet the target, encoding retains the lowest-error
safe candidate and reports a failed block. Thus a requested SNR is a selection
target, not a universal guarantee. This is a bounded greedy encoder, not a
globally optimal rate/distortion solver. Separate target runs are not guaranteed
to have monotonic rates because their carried states differ.

No final output clipping, gain normalization, brightness or DC removal occurs.
Finite/range failures above 1e6 are rejected rather than normalized. The old
emphasized-state +/-2 guard is retained to match its decoder kernel and is
independently counted before clamping. Candidates with guard hits cannot pass
the target. Every retained nine-case result has zero such events. IEEE-float
WAV preserves output overshoot above1; unit tests exercise that behavior.

## Complete LPV1 version1 format

All multibyte header fields are little-endian. Header size is 24 bytes.

| Offset | Field |
|---:|---|
| 0 | ASCII `LPV1` |
| 4 | version u8, 1 |
| 5 | flags u8, 0 |
| 6 | sample rate u16 |
| 8 | sample count u32 |
| 12 | embedded LPC2 bytes u32 |
| 16 | block samples u16, normally75 at7500Hz |
| 18 | width-profile count u16, 5 |
| 20 | block count u32, ceil(samples/block_samples) |

The complete LPC2 base follows, then a continuous LSB-first block bitstream.
Each block stores a 3-bit index into `[2,3,4,6,8]`, an 8-bit logarithmic scale
code with the original LPX3 mapping, then its biased unsigned excitation codes
at the selected width. Only the final byte is padded with zero bits. The last
block's sample count is derived from the complete duration. Decoder rejects
unknown profiles, truncated/extra bytes, nonzero padding and base/header
duration/rate mismatches.

Total bytes are `24 + base_bytes + ceil(sum(11 + block_samples_i*width_i)/8)`.
Reports separate header/base/block-header/code/padding costs. Decoder code,
runtime coefficient cache and memory are not included in the container size.

## Reproduce

```powershell
python tools/probe-lpc-vbr.py --reference original.wav --base base.lp2 `
  --output build/lpc-vbr/example --targets 20 24 28
python tools/test-lpc-vbr.py
```

Without `--base`, the original native LPC2 adapter builds one. `--fixed-root`
reuses existing fixed controls after checking that the embedded base is equal.
Otherwise the original LPX3 2/3/4-bit and separate LPX4 6/8-bit profiles are
encoded as controls. They retain their original output-clamping policy; LPV1
does not. Every report includes raw SNR, STOI/eSTOI, whole spectrogram components,
complete encoded bytes, failed blocks, guard counts, source/input fingerprints
and a separate parameter-only native decode equality check.

Six tests cover canonical mixed-width packing, padding/profile rejection,
independent scalar stateful decoding, samplewise causal feedback recovery,
unclipped overshoot and honest infeasible/minimum-width outcomes. Results and
the important English intelligibility tradeoff are retained in
`../research/lpc-vbr/README.md`.
