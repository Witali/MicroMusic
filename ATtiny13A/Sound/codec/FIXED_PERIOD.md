# Integer speech decoder and AVR transfer

The independent integer specification is [`fixed_period.py`](fixed_period.py).
The runtime is handwritten AVR assembly in [`fixed/firmware.S`](fixed/firmware.S).
The new speech model is **not yet a complete ATtiny13 speech release**: real
speech code plus data still exceeds its 1024-byte Flash limit. The original
HQ4/HQ4-T firmware and public player remain the references.

## Integer arithmetic

`period-fixed-v1` generates unsigned 8-bit PWM at 7500 Hz, with a 64-sample hop.
It retains continuous 16-bit phase, sixteen 32-tap signed 4-bit waveforms,
phase interpolation and a fade between frame centers. The phase pitch changes
at block starts; these are two different clocks. The AVR implementation currently
supports four fractional phase bits. The PC specification additionally allows
five or six for comparison.

The full-gain wave is scaled by sixteen. Gains are zero, 1/32, 1/16, 1/8, 1/4,
1/2, 3/4 and one. Residual excitation comes from a 16-bit Galois LFSR advanced
eight times per sample. White high-band noise is a first difference; colored
noise uses a symmetric 15-tap FIR. Parameter validation bounds each FIR's full
coefficient absolute sum to seventeen, keeping all specified products in int16.

Signed shifts round toward negative infinity; explicit rounding ties go toward
positive infinity. Each frame sum saturates before temporal interpolation.
An optional two-byte DC estimator runs after the blend; its state persists across
phrase repeats while phase and noise restart. See [`dc_blocker.py`](dc_blocker.py)
and the [DC measurements](../research/dc-output/README.md). The approved waveform
is not mirrored or forcibly made symmetric.

Converting a floating model changes its arithmetic and amplitude conventions.
`from_colored` is a starting point for **automatic retuning**, not a lossless
conversion. The encoder now renders actual integer output, including DC removal,
and scores that output against the original. It can minimize spectral error under
a fixed STOI floor and preserve the supported modes of a compact decoder.

## Data and target specialization

The portable PF header is twelve bytes: little-endian `<4sHHHBB>` containing
`PF\x01\x00`, sample count, initial phase, noise seed, phase fractional precision
and DC shift (zero disables it). It is followed by 256 packed waveform bytes,
twelve packed symmetric FIR bytes and the sequential compact frame fields.
`pack_fixed`/`unpack_fixed` preserve target PCM, including zero-amplitude field
canonicalization and exact padding checks.

AVR embeds metadata as assembly constants and uses a separate data layout:
biased packed wave taps, zero/one/three expanded FIR tables, then the same frame
field stream. `avr_features` derives compile-time choices from the actual model:

- omit the unvoiced base generator if no active frame uses it;
- omit FIR code and tables when all active residuals are white;
- share one FIR table if all three filter rows are identical;
- omit unused trailing wave words;
- shorten the noise history to two bytes when FIR is absent.

These omissions preserve every PCM byte for the supplied model. They are distinct
from the automatic parameter changes that produced the single-FIR and white-only
models. Target profiles and exports are described in [`OUTPUT_TARGETS.md`](OUTPUT_TARGETS.md).

## Verification and remaining limits

`tools/test-speech-quality.py` includes integer packing, bounds, DC, target exports,
search and existing speech-model tests. `tools/test-fixed-avr-kernels.py` assembles
the actual source sections into fixtures that fit the real ROM. Independent
expected values cover all gains, every table point, interpolation, signed FIR,
negative boundaries, saturation, DC, phase/noise state and all compact pitch
prefixes. The retained [kernel report](../research/fixed-period/avr-kernels.json)
records 122192 calls and 1208 parsed frames **per JS/WASM engine**.

The [full control validation](../research/fixed-period/validation/build.json)
uses two wave words and six changing synthetic frames. Its complete 876-byte
firmware produces 1152 exact samples over three loops in JS, optimized WASM and
unoptimized WASM. This exercises the actual timer, parser, two clocks, waveform
fade, phase, noise and continuous DC state. It is a functional validation fixture,
not the full speech recording and not a physical hardware test.

Real speech models, automatic-search records and alternatives are retained in
[`research/fixed-period/chego`](../research/fixed-period/chego/README.md). Assembly
reports in that directory distinguish code, tables and total Flash. Oversized
models produce a measured relocatable object and an `oversized` report; neither
the linker cap nor the production emulator is expanded to accommodate them.

The complete speech stream still needs substantial size reduction. Full-stream
cycle deadlines for colored speech remain open even though arithmetic fixtures
pass: an isolated render timing is not the cost of two renders plus noise, parser,
DC and interrupts. SRAM/stack measurements from a smaller fixture also do not
establish the worst case of an oversized recording.

Current AVR control additionally requires a whole number of 64-sample blocks,
at most 255 blocks (16320 samples), and phase precision four. The builder rejects
other cases explicitly. Longer speech, other MCU timer maps and hardware
multiplication are tracked in the [development plan](SPEECH_QUALITY_PLAN.md).

Useful optimization sources and the old Mini-LPC comparison are collected in
[`AVR_ASSEMBLY_RECIPES.md`](AVR_ASSEMBLY_RECIPES.md).
