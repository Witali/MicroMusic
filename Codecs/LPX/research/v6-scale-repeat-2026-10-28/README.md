# Isolated scale-repeat prototype

The bounded pilot is complete and further work is paused. The four fixed tuning
chains **grow by 14, 18, 24 and 36 bytes of complete Flash**. One long reset
chain saves 28 bytes. Production remains V5 with no new default. Saving this
checkpoint does not resume optimization or expand the corpus.

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
step is attempted. No persistent class member was added. The completed pilot
measures unchanged 756 B static SRAM and unchanged observed stack margins.

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

## Completed bounded pilot

The fixed selection was manifest indices 0/1 and 40/41 from the tuning split,
index 85 as one long-chain correctness control, and three synthetic boundaries.
No result changed that selection or the scale-only tuning nomination. Each of
the eight cases has separate original V5 and derived V6 complete player images
at normal and +100-cycle IRQ load: **32 ASM images**. Two additional explicit-C
images use the fixed 64,000-sample profile-6 tuning control. Nothing was dropped;
all 34 images fit within 32,768 B Flash. This is not the full frozen corpus.

Complete-player Flash is actual linked `.text + .data`, including code, tables,
headers, exact ordered audio segments, directories and linker layout. Positive
saved bytes mean a smaller complete image. The paired ASM deltas are identical
at normal and +100 IRQ load:

| Anonymous control | Profile / samples / segments | Data saved, B | Program growth, B | Net complete Flash saved, B |
| --- | --- | ---: | ---: | ---: |
| tuning index 00 | 4 / 64,000 / 1 | 33 | 47 | **-14** |
| tuning index 01 | 6 / 64,000 / 1 | 29 | 47 | **-18** |
| tuning index 40 | 4 / 32,000 / 1 | 22 | 46 | **-24** |
| tuning index 41 | 6 / 32,000 / 1 | 10 | 46 | **-36** |
| long correctness index 85 | 6 / 281,632 / 5 | 74 | 46 | **28** |
| synthetic partial tail | 4 / 1 / 1 | 0 | 46 | -46 |
| synthetic partial tail | 6 / 180 / 1 | -1 | 47 | -48 |
| synthetic nonzero repeated scale | 6 / 320 / 1 | -1 | 45 | -46 |

The long chain measures 27,850 -> 27,822 B complete Flash at normal load and
27,858 -> 27,830 B stressed. The code/table/directory cost grows while stored
audio shrinks by 74 B. The measured 28 B net gain applies to this chain; the
four tuning losses prevent a general size-win or adoption claim. The 45..47 B
program delta varies with linked layout; it is not a portable constant.

All 32 ASM images pass complete physical PWM equality, exact produced/played
sample counts, EOF, timer ticks/events, empty queue termination, zero decoder
or observer errors, zero underruns, and positive stack margin. Together they
verify **1,896,532 physical output ticks**. Static `.data + .bss` is 756 B in
all 34 images. ASM stack margin is 1,231 B on speech/long controls and 1,240 B
on the short synthetic controls, unchanged between versions; explicit C retains
1,219 B. The configured queue is 256 B with prefill 192 samples; shorter streams
can finish before reaching that prefill.

Both C versions reconstruct all 64,000 valid PWM samples exactly, with zero
decoder/observer errors, but V5 has **36,410 underruns / 100,410 ticks** and V6
has **36,416 underruns / 100,416 ticks**. They fail the 8 kHz timing admission.
In the original receipt fields `full_pwm_exact`, `all_full_pwm_exact` and
`both_complete_pwm_exact`, equality compares the observer's retained **valid
samples**. It implies full physical tick equality only when underruns are zero
and tick counts match. C inserts idle ticks, so its physical output is not
equivalent in real time. C remains explicitly selectable; this is an arithmetic
and valid-sample correctness observation, not C real-time support.

The already completed independent audit rechecked 34 ELF images and 50 exact
embedded segment regions, regenerated their binary representation from the ELF,
rechecked linked size and current source/toolchain/runtime/adapter bindings, and
compared 2,024,532 retained valid PWM samples including the two C observations.
It retained both timing failures. Five focused test groups passed before the
pilot. The study took 166.39 s and the independent audit 4.40 s. These are
simulator results; no physical board measurement or audibility improvement is
claimed. Output equality is the requirement.

## Saved evidence and recipe

`pilot-summary.json`, `pilot-rows.json` and `pilot-audit.json` are exact copies
of the completed anonymous receipts. `pilot-source-runtime.json` preserves the
original source/runtime fields except the raw local native compiler wrapper/version
line, which remains private; the omission
is labeled in that file. No source hash, measurement or runtime value was changed.
`checkpoint.json` states the paused scope and clarifies the PWM field names.
`pilot-compiler-recipe.json` retains shared compiler/header/library hashes,
flags, harness identity and source variants without per-recording fingerprints.
The existing measured `prototype/pilot.py` and independent
`reproduction/audit_pilot.py` are retained unchanged; their source hashes bind
the receipts. Private manifests, original/experimental audio, media/PCM/ELF
fingerprints, images, paths and logs remain in ignored local `build/` receipts.

The recipe below documents the completed run for a later explicitly authorized
reproduction. It was not rerun when saving the checkpoint. Supply the frozen
manifest and local toolchain/runtime paths through environment variables:

```sh
python Codecs/LPX/research/v6-scale-repeat-2026-10-28/prototype/pilot.py \
  "$LPX_BASELINE_MANIFEST" build/scale-repeat-replay \
  --avr-bin "$LPX_AVR_BIN" --include "$LPX_SIMAVR_INCLUDE" \
  --lib "$LPX_SIMAVR_LIB" --wsl "$LPX_WSL"
python Codecs/LPX/research/v6-scale-repeat-2026-10-28/reproduction/audit_pilot.py \
  build/scale-repeat-replay "$LPX_BASELINE_MANIFEST" \
  build/scale-repeat-replay/audit.json \
  --avr-bin "$LPX_AVR_BIN" --lib "$LPX_SIMAVR_LIB" --wsl "$LPX_WSL"
```

Use Python 3.12 and the source/runtime versions recorded in the receipts. Do
not use Python optimization flags: the independent audit uses assertions.
The pilot is a frozen-manifest research recipe; a failed admission remains
visible instead of changing a quality or timing gate. No native decode, AVR
build or new experiment was needed to export this checkpoint.

Full frozen corpus expansion, alternate syntax/parser work, simultaneous V5+V6
support costs and an adoption decision remain unperformed and paused. The
production decoder and player are unchanged.
