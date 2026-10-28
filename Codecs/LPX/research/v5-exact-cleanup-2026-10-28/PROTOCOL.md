# Exact v5 optional-pulse cleanup

This deterministic host-only pass preserves decoded PCM/PWM relative to its
input v5 stream. V5 remains lossy relative to an original WAV. The pass changes
no MCU code, format, spectra, scale/lag/gain, base pulses, pre-emphasis or
brightness, and uses no subjective metric or tuning.

For every played sample, let

```text
q[i] = clamp(((gain[i] * q[i-lag[i]] + 8) >> 4) + base[i] + extra[i], -32, 31)
drive[i] = q[i] * scale_table[scale_code[i] * 8]
```

History is zero before each real reset. Parameters apply to 160 samples and
base pulses to 20 samples; one optional pulse belongs to each stored 40-sample
chunk. Lag is 18–145, gain is an even integer 0–14, and the actual scale table
has zero entries for multiple legal scale codes. Signed division/shift and
both asymmetric saturation bounds must remain exact.

Initialize a liveness mask for all played samples with nonzero actual scale
step. Traverse samples backwards. A live sample with nonzero gain marks its
nonnegative lag predecessor live. Positive lag makes this a causal DAG; the
mask is conservative because it does not exploit clipping or pitch rounding
to erase dependencies.

Remove extras at unplayed tail coordinates or at unmarked q coordinates. For
every marked q, all its relevant predecessors remain marked and unchanged by
induction. Unmarked coordinates can change but have zero direct drive and no
path to a nonzero drive. Walk the cleaned ring forwards and remove each remaining
extra only if the clipped q with and without it is identical. That substitution
also leaves all future states identical. The implementation checks every live
q and every drive against a separately maintained original ring. Identical
drive, untouched coefficients/parameters and identical reset state preserve
the entire LPC, de-emphasis, clipping, brightness, PCM and PWM pipeline.

Canonical repack is measured before active removal with the original extras
layer forced. Legal marker1/amplitude0 fields are canonicalized and reported;
nonminimal Rice/spectrum syntax may also shrink. Dead active, clipping-equivalent
active, and final empty-marker-layer savings are separate byte stages. Padding
is counted through actual serialization at each stage. Every mandatory stored
320-sample packet, including its unplayed fields, remains present.

`cleanup_speech_compact.cleanup(blob, common=..., compact_only=...)` returns only
after non-growth, exact non-extra fields, a private-transform fixed-point check,
and complete integer-model/common/v5-only native PCM/PWM equality. It snapshots
mutable input and does not recursively call public validation for idempotence.
Missing sessions are created with the explicit common/v5 layouts. Reuse sessions
for corpus work. The CLI protects its input and writes only an admitted output.

Seven independent component groups cover a full-history scalar q oracle and
explicit-set DAG oracle, zero-step history followed by zero/nonzero feedback,
both saturation signs and opposite-sign ties, legal zero-amplitude markers,
noncanonical Rice escapes, fourteen packet/tail boundaries, 48 deterministic
random fixtures, a 64,000-sample stream, fixed point/ownership, malformed streams
and native mismatch rejection. The random seed is test data, not corpus tuning.

The fixed corpus scope is all 181 original references: original speech 98
profile groups, non-speech 264, and accepted expanded100 speech 98, totaling
460 source/profile groups. Also include every available finalized combined-study
selected/raw chain. Deduplicate actual ordered streams; apply the q graph
independently at each explicit reset. Preserve all original sources and keep
recording, stream, PCM, image fingerprints and media paths in ignored storage.

Before claiming firmware savings, measure changed Flash-fitting old/new chains
on the complete current ATmega328P production player, queue256/prefill192,
explicit ASM, full durations, normal/+100 IRQ. Require exact PWM/EOF/ticks,
zero underruns/errors, non-growth and positive observed stack margin. Full Flash
means linked `.text + .data`; count every embedded stream/header/tail/alignment
byte. Long music that cannot fit the MCU image remains explicitly host-only.
This protocol predeclares no expected saving and no listening claim: any benefit
must survive exact equality, real serialization and actual linked image cost.
