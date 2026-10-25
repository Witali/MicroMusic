# Optional compact L4HY v3

This post-packer preserves decoded LSF, excitation q, PCM16 and PWM. It is
applied **after** v2 analysis/optimization. Existing v2 readers reject v3;
the portable core accepts it only with an explicit `LPX4_V3_FEATURES` mask.
The default remains zero (v2 only). This macro selects container parsing,
independently of C/ASM arithmetic and hardware Flash access.

The 20-byte header layout, sample rate/count, Q14 parameters, 160-sample
frames and 80/40-sample blocks/subframes are unchanged. Version is 3.
Flags must contain low bits `3`; the following optional bits are allowed.
All fields remain LSB-first with only final-byte padding.

| Mask bit | Encoding | Existing state reused |
| --- | --- | --- |
| 4 | Scale: `0` repeats; `1` precedes the v2 scale-delta code | Previous scale, initially 0 |
| 8 | Width: `0` repeats; `1` precedes the v2 3-bit width | Previous width, initially 0 |
| 16 | Subheader: `0` repeats; `1` precedes v2 type/parameters | Previous type/k/lag/gain, initially direct/k0 |
| 32 | Width 0 omits scale and all subframe fields | Keep scale; implied direct/k0; write zeros into q ring |
| 64 | LSF delta frame uses a 2-bit selector instead of the v2 1-bit selector | Previous LSF vector |

For bit 16 a direct descriptor is `(type=0,k)`, exact is `(type=1,lag,gain,k)`,
sparse is `(type=2,lag,gain)`. Sparse **always** transmits count (4 bits)
and its position/amplitude pairs, including after repeated descriptors.
Repeated descriptors do not bypass current-width/range/pulse validation.
Partial subframes obey the same sample count and pulse bounds as v2.
Implicit zero subframes reset the preceding descriptor to direct/k0.

Bit 32 still reads every LSF frame and runs LPC/postfilters for every sample.
Scale context is unchanged across zero-width blocks, so the next nonzero
scale is delta-coded against the last transmitted scale. No audio-state
reset, silence shortcut or skipped samples are permitted.

For bit 64 the delta selectors are `00` v2 plane, `01` signed byte, `10`
Rice k0 and `11` Rice k2. Zigzag is `2*d` for nonnegative d, `-2*d-1` otherwise.
Rice quotient <8 is quotient zeros, one stop bit, k remainder bits. Eight
zeros instead introduce an **8-bit signed byte escape**, with no stop or
remainder. At most 16 bits are consumed per delta. Frame repeat (`0`) and
absolute (`1,0`, ten 10-bit values) retain v2 syntax. Delta starts `1,1`.
The offline encoder selects the shortest complete delta vector.

The optional parser adds one byte of object state (`formatFeatures_`):
measured static SRAM is 1101 → 1102 bytes in the default harness and
845 → 846 bytes in the compact harness.
No new arithmetic tables, history vectors or per-sample dispatch are added.
Compile only the needed mask: e.g. `-DLPX4_V3_FEATURES=24` accepts v2 and
v3 streams using width/subheader bits; unsupported header bits are rejected.
Define the mask consistently for **all translation units**, since it changes
the class layout. The AVR5 arithmetic still needs its separate explicit ASM
enable flag.

```sh
# Explicit size experiment, including native PCM16 parity.
python tools/compact_format.py input-v2.l4hy output-v3.l4hy --features 24 --report compact.json
# Zero-heavy data; compare complete firmware Flash and measured time as well.
python tools/compact_format.py input-v2.l4hy output.l4hy --features 40 \
  --avr-bin /path/to/avr/bin --sim-runner /path/to/sim_profile \
  --timing-work build/compact-gate --report compact.json
```

With the timing options the CLI emits v3 only if total ELF Flash, mean
decode time and maximum 160-sample window do not grow, and underruns are
zero. Otherwise it writes the original v2 stream and records the rollback.
SRAM is reported separately; the extra byte is an explicit v3 tradeoff.
Native C parity alone does not establish AVR real-time support.

Scale-repeat and LSF Rice are experiments rather than defaults: each can
increase total Flash for short streams. Measured workloads, break-even
costs and simulator limits are in
[the research report](../../research/q0-lossless-2026-10-25/README.md).
