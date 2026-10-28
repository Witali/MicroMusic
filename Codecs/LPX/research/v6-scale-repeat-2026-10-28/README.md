# Isolated scale-repeat prototype

This opt-in experiment reserves **L4HY version 6, selector 1** locally. Before
the prototype, source/tool/documentation searches at `9a89b1f8` found no L4HY v6
format. Historical **L3AV** v6 uses a different magic. This is a provisional
repository experiment, not an external format registry allocation or a new
default.

The production `01_ACTIVE_Q0_CODEC/src/` files remain byte-identical to
`5c7e0592`. `prototype/materialize.py` checks every source hash, applies the
retained `decoder-v6-scale-repeat-v1.patch` without fuzz, and writes the derived
decoder only under ignored `build/`. Original project provenance and licensing
remain applicable; no third-party implementation or new license is introduced.

## Exact syntax

The original 22-byte header shape is retained, with version byte 6. The uint16
payload length includes a first payload byte **1**, the fixed method selector.
Spectral syntax, profile/extras flags and excitation bits are unchanged.

The first 160-sample parameter tuple in each segment is absolute: scale 5 bits,
raw lag 7 bits, gain code 3 bits. Every later tuple starts with a scale marker:
0 retains the previous raw scale; 1 reads a new absolute 5-bit scale. It then
always stores the exact raw lag and gain code, even for zero gain or unplayed
mandatory tail tuples. There is no tuple alignment. Each complete segment has
its own final zero byte padding.

`scale_repeat.py` copies original raw spectral and excitation spans instead of
canonicalizing their values. It preserves deliberately nonminimal spectral
Rice codes, a forced extras flag with no active extra pulse, and legal marker
1 / amplitude 0. V5 -> V6 -> V5 must recover the original complete bytes.

The new decoder uses decoded `lag_ == 0` before the first tuple and retains
`blockStep_` for scale repeats. A decoded lag is always 18..145 afterward,
including for zero gain. Encoded lag code 0 means decoded lag 18. Scale aliases
are retained exactly by the host converter; no reverse lookup from derived
step is attempted. No persistent class member was added. Actual AVR SRAM and
stack still require measurement.

The derived compact build accepts experimental V6 only. The original V5-only
decoder is kept as a separate measured control; simultaneous V5+V6 decoding
is not included in this prototype's code-cost scope. The derived common build
retains the original legacy V2/V3/V4 branches. Its compact speech branch accepts
V6 in place of V5. Existing portable API, hardware Flash access and explicit
C/architecture-ASM backend gating are retained. No handwritten ASM was added.

## Validation and reproduction

The independent `reference.py` uses an indexed-bit cursor and separate bit-list
writer to reconstruct a complete V5 stream before invoking the old V5 model.
Experimental bytes are never merely relabeled or passed directly to that model.
Actual native and AVR decoders receive the experimental stream unchanged.

Run from the repository root with Python 3.12, NumPy, Numba, SciPy and a native
C++ compiler available:

```sh
python Codecs/LPX/research/v6-scale-repeat-2026-10-28/prototype/test_scale_repeat.py
python Codecs/LPX/research/v6-scale-repeat-2026-10-28/prototype/materialize.py \
  build/scale-repeat-v1/derived
```

Focused checks cover exact charged byte costs, every raw scale including aliases,
unused lag, forced/zero-amplitude extras, noncanonical spectra and sample tails
through 64,000; common/compact native PCM16 and PWM versus both explicit adapters;
reset/restart, sticky errors, copies/assignment and lag-zero lifetime; selector,
truncation/header bounds; alternate ROM cursor, Q4, history, anchor and remaining
counter settings; and frozen-source/output tamper protection.

Complete-player Flash includes actual code, tables, headers, ordered audio
segments and linker layout. A future pilot must preserve both original V5 and
experimental results at normal/+100 IRQ with complete PWM/EOF/tick/queue/stack
checks. C arithmetic remains explicitly selectable on AVR; offline correctness
does not establish C real-time support. No audibility improvement is expected
or claimed because the output is required to be exact.
