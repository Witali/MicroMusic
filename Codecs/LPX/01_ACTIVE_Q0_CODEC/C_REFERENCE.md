# Portable C reference backend

The active reference is `src/Lpx4HybridCore.cpp` with
`LPX4_ENABLE_ASM=0`, used by both the host batch API and the independent native
reference in firmware checks. Update this core/header when updating the small
AVR path. Historical `reference_v*` directories are frozen format baselines.

`tools/batch_decoder.py` now explicitly builds the C arithmetic backend.
The default `compact_version=5` preserves the previous feature selection.
For v9, select the same format in all translation units:

```python
from pathlib import Path
from batch_decoder import BatchSession

blob = Path('voice-v9.lpx').read_bytes()
samples = int.from_bytes(blob[5:7], 'little')
with BatchSession('batch', speech=True, speech_compact=True,
                  compact_only=True, compact_version=9) as reference:
    pcm16 = reference.decode_one_s16(blob, samples)
    pwm8 = reference.decode_one(blob, samples)
```

The array helpers require NumPy. Building the library and calling its native
C ABI require only the host compiler/runtime; NumPy is imported only when an
array helper is used. Direct builders accept `compact_version=9` as well:

```python
from batch_decoder import build_library
build_library(Path('build/reference-v9.so'), speech=True, speech_compact=True,
              compact_only=True, compact_version=9)
```

The C ABI reports its format through `lpx4_batch_compact_version()`. A prebuilt
library with the wrong format is rejected; older libraries without this
metadata are treated as the former version 5 configuration. The source cache
includes the format and all `Lpx4*` headers, including C arithmetic headers,
so an arithmetic-only update cannot leave the reference cache stale.

Both PCM16 and PWM batch entry points accept the v9 minimum 13-byte header and
drain the final false decode call. This validates trailing data even for a
partial sample tail. Invalid rows remain isolated from valid batch rows.

The v9 count is stored as a 16-bit word in both C and optimized builds, because
every serialized count fits that range, including rejected values up to 65535.
The public `samples()`/`produced()` interfaces still return 32-bit values.
Version 5 retains its former 32-bit field, including invalid-header metadata.

Rebuild the core and all C++ consumers together after a class-layout change;
the opaque native batch ABI and public output types are preserved.

## Optional floating synthesis

The default `LPX4_FLOAT_SYNTHESIS=0` keeps the fixed-point C reference and its
PCM16/PWM interfaces. Select `LPX4_FLOAT_SYNTHESIS=1` consistently in every
translation unit for floating synthesis. It requires IEEE754 `double` with
at least 53 significant bits and `LPX4_ENABLE_ASM=0`; enabling ASM and floating
synthesis together is a compile-time error. The parser and parameters stored
in the sound file are shared by both numeric modes.

Use the explicit floating batch API to retain its precision through output:

```python
with BatchSession('batch', speech=True, speech_compact=True,
                  compact_only=True, compact_version=9,
                  float_synthesis=True) as reference:
    samples_f64 = reference.decode_one_f64(blob, samples)
    pcm16 = reference.decode_one_s16(blob, samples)
    pwm8 = reference.decode_one(blob, samples)
```

`decode_many_f64` returns one NumPy `float64` array per valid stream, normalized
to `[-1,+1]`; invalid rows return `None`. It calls `nextFloat(double&)` directly,
including the final EOF validation call. It never passes through PCM16 or PWM.
No intermediate integer rounding is introduced by the batch bridge. Conversion
to a playback or file sample format belongs at the final output boundary. The
existing PCM16/PWM APIs remain available in floating mode through `nextS16()`
and `next()`: they quantize only the final output sample and retain floating
filter/history state. They do not switch synthesis back to fixed arithmetic.

The direct C ABI is `lpx4_batch_decode_f64` with the same concatenated input,
offset, size, count, stride, expected-count and per-row status arguments as the
PCM16 batch entry point; its output pointer is `double*` and stride is in
samples. `lpx4_batch_numeric_mode()` returns `0` for fixed and `1` for floating
synthesis. All output symbols remain present. Fixed builds cannot supply
unquantized f64: their f64 entry point returns `-5`, and Python reports a mode
error before calling it. Both fixed and floating builds provide PCM16/PWM.
Those output types do not identify which synthesis arithmetic was selected;
use numeric-mode metadata to distinguish them.

`build_library`, `cached_library`, `BatchDecoder` and `BatchSession` accept the
keyword `float_synthesis=True`. The source cache includes the numeric mode and
all `Lpx4*` helpers, and the builder explicitly defines the numeric mode.
Prebuilt libraries must match both the requested format and numeric mode.
Older libraries without numeric-mode metadata are treated as fixed. Unknown
modes or missing floating entry points are rejected. A floating request in
`mode='auto'` propagates a native build/load failure; it never falls back to an
integer subprocess. `mode='reference'` rejects floating requests because that
subprocess interface supplies only integer output. Default fixed-mode fallback
behavior is preserved.

The dependency-light batch controls are:

```sh
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_batch_float.py
```

They compare floating-mode native `double`, PCM16 and PWM samples against
independent `nextFloat()`, `nextS16()` and `next()` callers across profiles and
partial tails, check off-grid PCM16 values, protect row strides and EOF
validation, and exercise numeric-mode/cache/fallback contracts.
They require g++ and Python's standard library, without NumPy.

Run the dependency-light native checks with g++ and Python's standard library:

```sh
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_batch_v9.py
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_speech_v9.py
```

The first checks short v9 files, both output domains, EOF rejection, prebuilt
format selection, cache invalidation and the original subprocess C reference.
The second checks the complete pulse domain, both memory/cursor/count-update
profiles, file-defined filter parameters and invalid-count metadata. Full
AVR/IRQ checks additionally compare every PWM byte against the native C output.

The 1500-cycle optimization keeps all three arithmetic selections equivalent.
V9 packs three private flags and uses an eleventh discarded linear-history word;
`lpx4SynthesisQ12<q4,true>` explicitly opts into that layout, while the default
helper still accepts ten words. The C reference performs the same history shift.
Universal SRAM512 v5/v9 builds compute only the exactly symmetric half of P.
Q keeps its full recurrence because negative floor rounding breaks antisymmetry.
The standard-memory C path retains the full polynomial calculation as an oracle.
No recording parameter or compressed byte is moved into the decoder build.

V9 now accepts profiles4,6 and15 in the same C/ASM build. Profile15 carries
the former v8 sparse80 excitation: one signed innovation per80 samples and
scale/pitch metadata per320 samples. Both backends read the same runtime header.
Legacy v5 selection and its optional v8 reader remain available.

The v9 reader converts sorted packet positions into countdown gaps once per
packet. The shared sample loop decrements only the pending gap; it needs no
packet-phase multiplication. Its byte excitation accumulator is exact: the
rounded pitch term is in -28..27 and merged innovations in -16..16. Saturation
to the six-bit pitch history remains unchanged. These changes are in the C
reference too; they do not change P4/P6 compressed bytes or output.

The current seven native v9 tests also compare sparse80 against an ordinary
v5/P6 expansion in the standard-memory C reference, exercise every position
and sign, partial tails, profile switching, malformed input, and a public
2 kbit/s fixture with frozen PCM/PWM hashes. The22-case full-IRQ admission is
[retained separately](examples/ATTINY88_V5_PLAYER/v9-sparse80-measurements.json).

The later exact C word-extraction implementation passes real-time playback on
ATmega328P at 16 MHz with `LPX4_ENABLE_ASM=0`, while keeping fixed PCM/PWM
unchanged. [Current C measurements and equations](../../../docs/avr-asm-cookbook/lpx-fixed-c-realtime.md)
are separate from those historical receipts. An explicit source transition
preserves the old receipts and byte-identical shipped ASM images. Use
`tests/verify_atmega328p_v9.py --current-source` for the current C/ASM check.
