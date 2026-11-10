# LPX v9: compact playback without changing the audio

V9 repacks v5 P4/P6 and v8 sparse80 streams without re-analysis, quantization or resampling.
It preserves every decoded PCM16/PWM sample. All variable recording parameters
remain in the file. The decoder still supports 8 kHz and 1..64000 samples per
segment, with the same 16-bit bounded input API.

## Header

All multibyte words are little-endian. The header is 13 bytes; v5 uses 22.

| Byte offset | Bytes | Meaning |
| --- | ---: | --- |
| 0 | 2 | ASCII `L9`, identifying version 9 |
| 2 | 1 | Profile 4 or 6, optionally OR 128 for extra-pulse markers; or 15 for sparse80 |
| 3 | 2 | Sample rate, currently 8000 |
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

Reject `high >= 25`. A25-byte Flash table returns
`((high % 5) << 2) | ((high / 5) << 5)`. Combine the two low coordinate bits
with the corresponding table bits. This removes runtime division by 20 and
its constant software products on AVR25. All 400 pairs remain representable
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

## Tools and selection

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
Browser previews and existing published v5 streams keep their existing format.

The current universal v9 Tiny88 player uses FIFO32/prefill24 and a38-cycle
complete IRQ. Its22-case admission, including sparse80 boundary cases and a
real1.93 kbit/s phrase, is recorded in
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
