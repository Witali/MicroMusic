# LPX v9: compact playback without changing the audio

V9 repacks v5 P4/P6 and v8 sparse80 streams without re-analysis, quantization or resampling.
It preserves every decoded PCM16/PWM sample. All variable recording parameters
remain in the file. The v9 decoder supports 8, 12 and 16 kHz and 1..64000 samples per
segment, with the same 16-bit bounded input API.

For a single longer Web/PC stream, see the separately marked, opt-in
[V9 Long extension](LPX9_LONG_FORMAT.md). Ordinary V9/AVR limits remain unchanged.
The optional [whole-file gain extension](LPX9_GAIN_FORMAT.md) adds one output
coefficient for updated Web/PC/MCU decoders; unmarked files retain this layout.

## Header

All multibyte words are little-endian. The header is 13 bytes; v5 uses 22.

| Byte offset | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 2 | ASCII `L9`, identifying version 9 |
| 2 | 1 | Profile 4 or 6, optionally OR 128 for extra-pulse markers; or 15 for sparse80 |
| 3 | 2 | Nominal sample rate: 8000, 12000 or 16000 Hz |
| 5 | 2 | Sample count, 1..64000 |
| 7 | 2 | Pre-emphasis coefficient Q14, 0..16384 |
| 9 | 2 | Brightness coefficient Q14, 0..11469 |
| 11 | 2 | Payload byte count, exactly file size minus 13 |

Frame 320, block 160 and pulse-packet 40 sample geometry applies to P4/P6.
Profile15 uses block320 and one pulse per80 samples, with six-bit spectra.
It is not repeated in each file. The runtime API retains wide sample metadata;
the narrower count removes bits outside its already supported range.
The active C and optimized v9 cores also store this count as a word internally;
public sample/progress metadata stays 32-bit, including rejected-count values.

## Payload

Bits remain LSB-first. The spectrum packet at each 320-sample boundary uses
the same gap/delta/repeat representation and bounded Rice escape as v5.
The LPC conversion, interpolation, excitation, rounding, clipping and output
filters are shared with v5, using the same selectable C/ASM arithmetic.

Profile15 shares that synthesis, but writes scale5/gain3 once per320 samples
and one position6/sign1 field per80 samples. Position code `c` maps to
`c + ((c + 2) >> 2)`; sign0 means -8, sign1 means +7. As in P4/P6, lag7
is present only for nonzero gain. Its packet widths and geometry are selected
by the file's profile byte; there is no recording-specific decoder build.

Each 160-sample block begins with scale 5 and gain 3. If gain is nonzero, lag 7
follows and represents lag minus 18. With gain zero, lag is omitted and the
decoder uses 18. This is exact: `(0 * history + 8) >> 4` is zero for every
history value, so the omitted lag cannot change excitation or future state.

P4 keeps two position 4/sign 1 pulses per 40-sample packet. The decoder reads
each position/sign together as one 5-bit field.

P6 keeps two amplitudes 4 and exactly nine position bits. For positions `x,y`
in 0..19, store:

```text
low  = (x & 3) | ((y & 3) << 2)       // four bits, first
high = (x >> 2) + 5 * (y >> 2)        // five bits, second
```

Reject `high >= 25`. The reference 25-byte lookup returns
`((high % 5) << 2) | ((high / 5) << 5)`. Combine the two low coordinate bits
with the corresponding table bits. This removes runtime division by 20 and
its constant software products on AVR25. The universal AVR5 ROM path instead
computes the bounded quotient with hardware MUL and derives both coordinates
directly, without the lookup. Both paths keep the same wire representation.
All 400 pairs remain representable
in nine bits. Amplitudes and optional extra-pulse markers/positions remain
identical to v5.

Store only block headers and40-sample pulse packets whose starting sample
precedes the declared end. A partial40-sample packet still stores both pulses,
because the decoder reads them together. Later padded packets are omitted.
For profile15 this rule applies to80-sample packets instead.
Unused high bits of the final byte must be zero. Consume `next()` until it
returns false, then check `error()`; v9 validates payload exhaustion on that
final false call, including partial sample tails.

These changes never add payload bits when converting a valid v5 file:
spectral bits and active pulse widths stay the same, while zero-gain lag fields
and unplayed fields disappear. Including the shorter header, the new file is
at least nine bytes smaller. Converting back to v5 restores a complete final
packet with valid defaults and lag 18 at zero gain. Ignored original fields
are not reconstructed byte-for-byte; decoded audio stays exact.
The same rules remove at least nine bytes from a valid v8 sparse80 file.
Use `--version 8` to restore its long header and complete final packets;
profile15 cannot be serialized as ordinary v5 (the independent reference
adapter instead expands it to P6 with zero innovations between sparse pulses).

## Sampling rates

The rate field already existed; supporting 12/16 kHz adds no header or payload
bytes. Legacy v4/v5/v8 retain their 8 kHz contract. Repacking v9 preserves its
rate, and conversion to a legacy format rejects higher rates. AVR firmware
selects one rate at compilation with `LPX4_SAMPLE_RATE=8000`, `12000` or
`16000` (default 8000). The file rate must match. The portable PC reference
defaults to zero, accepting all three rates. `LPX4_EXTENDED_SAMPLE_RATES=0`
retains the explicit 8 kHz-only C/library compatibility mode.

Geometry remains defined in samples: a 320-sample frame lasts 40, 26.667 or
20 ms at 8/12/16 kHz. Higher-rate encoding must resample source audio before
analysis. Merely changing an existing file's rate changes playback speed.
The selected-rate P4/P6 encoder keeps the existing search; higher rates raise
the actual bitrate and change the physical pitch range. Existing 8 kHz
payloads and decoded samples remain unchanged.

Use `tools/speech_v9_audio.py encode --sample-rate 12000` or `16000`, and its
`decode` subcommand to write WAV at the stored rate. See the
[encoder commands, AVR clock divisors and IRQ admission rules](../../../docs/avr-asm-cookbook/lpx-sample-rates.md).

## Tools and selection

### Encoder bitrate presets

The shared C++ encoder offers **3 and 8 kbit/s complete-file ceilings** at
8000 Hz through `enc_bitrate(samples, kbps, rate, autoQuiet, calls)`. These
are encoder settings, not new wire-profile numbers or codec versions:

| Encoder preset | Existing V9 wire mode | Budget allocation |
| --- | --- | --- |
| 3 kbit/s | P4 (profile byte 4) | Energy-weighted spectral holding and closed-loop excitation search |
| 8 kbit/s | P6 (optionally extra-pulse bit 128) | Shared adaptive search with budgeted existing extra pulses |

The cap is `floor(samples * kbps * 1000 / (8 * 8000))` bytes, counting the
ordinary 13-byte or Long 17-byte header and every stored payload/tail bit.
The chosen file may be smaller; no filler is added to meet a nominal rate.
Very short inputs may have no candidate under the cap. The search returns an
explicit no-fit error without truncating samples or changing playback rate.
The ordinary P4/P6 modes retain their existing rate and allowance settings.

The new presets use the same decoder, fields, rounding, final-padding/EOF
validation and continuous state as every other V9 stream. For input over
64000 samples, the existing V9 Long host marker is used; AVR limits stay as
documented in [LPX9_LONG_FORMAT.md](LPX9_LONG_FORMAT.md).

Native C++ and scalar/SIMD WASM execute the same preset code. The browser
selector includes both presets. Prepared mono PCM16/8000 Hz WAV can also be
encoded locally on a PC, without Python:

```text
node web-player/scripts/encode-lpx.mjs input-8khz.wav new-3k.lpx --kbps 3
node web-player/scripts/encode-lpx.mjs input-8khz.wav new-8k.lpx --kbps 8 --backend simd
```

Previously selected v5 3 kbit/s streams can still use the lossless repacker
below and retain every decoded sample. The new bounded C++ search is not a
claim of identical candidate selection to the older Python search. Legacy
v2/v3 LPX8 must be re-encoded from its source audio; the presets do not wrap
another decoder or promise lossless conversion from arbitrary legacy data.
See [validation and measured AVR costs](../research/v9-bitrate-presets-2026-11-23/README.md).

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/speech_v9.py input.lpx build/voice-v9.lpx
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/verify_attiny88_player.py \
  build/voice-v9.lpx build/voice-v9-player --wsl Ubuntu
```

The Tiny88 builder detects `L9` and selects `LPX4_COMPACT_VERSION=9`.
It does not pin profile, filters or other recording parameters. The same v9
decoder can read every supported P4/P6/15 header. Existing v5/v8 inputs retain
their former builder paths.

For direct library use, compile all consumers and the core with
`-include profiles/Lpx4Sram512.h -DLPX4_COMPACT_VERSION=9`. Standard-memory
compact-only configurations also work. Version5 remains the default; v9
requires compact-only decoding and includes sparse80 automatically. The legacy
v5 build still requires `LPX4_ENABLE_SPARSE80=1` to accept v8/15. Select C with
`LPX4_ENABLE_ASM=0`; ASM additionally needs a supported real target and explicit
enable. Format, arithmetic and Flash/input-source selection are independent.
WebUI AVR images embed v9. Browser previews use their catalog's declared
stream format; existing legacy files remain available through legacy builds.

The current universal v9 player uses FIFO32/prefill24 and a complete ASM IRQ
of 35 cycles on Tiny / 35..36 on Nano, depending on the linked vector.
The [132-case rate matrix](../research/avr-player-3k-2026-11-17/sampling-rates.json)
checks 22 workloads on both CPUs at 8/12/16 kHz, retaining unadmitted Tiny
high-rate cases. The original 38-cycle sparse80 admission, including a
real 1.93 kbit/s phrase, remains recorded in
[the source-bound report](examples/ATTINY88_V5_PLAYER/v9-sparse80-measurements.json).
The older comparison below is retained as a historical P4/P6 baseline.

Reproduce the matched full-IRQ comparison and portable reader checks:

```sh
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_attiny88_v9.py build/v9 --wsl Ubuntu
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests -p test_speech_v9.py
```

The native tests need g++. They compare PCM16/PWM, all 400 valid pulse pairs,
all112 invalid codes, 60 header combinations, sample tails, the 64000-sample
boundary, ROM/callback switching, both cursor modes, both memory profiles and
both remaining-count strategies. The separate AVR run compares full playback
on fourteen workloads against the v5 decoder with interrupts active.

[Portable C reference and batch-library selection](C_REFERENCE.md) explains
version9 reference builds, cache freshness and strict batch EOF validation.
