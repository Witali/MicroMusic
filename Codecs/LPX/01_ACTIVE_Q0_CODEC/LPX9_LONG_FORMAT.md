# LPX V9 Long: one continuous host stream

This optional Web/PC extension removes the ordinary V9 64000-sample and
65535-byte limits. It is one header and one continuous V9 payload, with no
segment table, concatenated streams, state resets or padding between segments.
Pitch history, LPC interpolation and output filters continue for the whole file.
Payload geometry and integer synthesis are identical to ordinary V9.

## Header

All words are little-endian. Bit6 of the profile byte marks a 17-byte Long header.
Bit7 retains its existing extra-pulse meaning for P4/P6. The low six profile bits
remain 4, 6 or 15; Sparse80 does not allow the extra-pulse bit.

| Offset | Bytes | Field |
| --- | ---: | --- |
| 0 | 2 | ASCII `L9` |
| 2 | 1 | Profile OR `0x40`, optionally OR `0x80` for P4/P6 extras |
| 3 | 2 | Rate: 8000, 12000 or 16000 Hz |
| 5 | 4 | Nonzero sample count, uint32 |
| 9 | 2 | Pre-emphasis Q14, 0..16384 |
| 11 | 2 | Brightness Q14, 0..11469 |
| 13 | 4 | Payload bytes, exactly file size minus 17 |

When bit6 is clear, the original 13-byte V9 header and all its limits still
apply. Promoting a valid short V9 header to Long leaves its payload and every
decoded sample unchanged. The browser encoder writes ordinary V9 for <=64000
samples and Long for longer inputs. It never changes or truncates the rate.
V9 final-packet omission, strict EOF and zero-bit padding rules also apply here.

## C and WebAssembly selection

`LPX4_ENABLE_WIDE_V9=1` enables `beginWideV9(const uint8_t*, uint32_t)` in the
standard-memory, compact-only V9 C core. Define it consistently for all consumers:

```text
-DLPX4_ENABLE_ASM=0 -DLPX4_ENABLE_SPEECH=1
-DLPX4_ENABLE_SPEECH_COMPACT=1 -DLPX4_COMPACT_ONLY=1
-DLPX4_COMPACT_VERSION=9 -DLPX4_ENABLE_WIDE_V9=1
```

The opt-in build accepts both headers. The default is zero: existing 16-bit
`begin()`/callback interfaces and AVR object layouts retain their existing
behavior and reject the Long marker. This extension is intentionally unsupported
on AVR; do not pass Long files to existing AVR builders or firmware.

The web application caps either stream at 32 million samples and 100 MiB of
compressed input to bound allocations. Encoder memory grows with input length,
up to 1 GiB of WASM linear memory; the decoder permits 256 MiB. Original browser
audio and copied PCM use additional memory. These are application resource
limits, not restrictions of the uint32 fields. Allocation failures are reported.

`node web-player/scripts/decode-lpx.mjs input.lpx output.wav` decodes either
header on a PC using the same import-free C/WASM module. Output must not exist.

## Verification

`web-player/tests/lpx-browser.test.mjs` covers promoted legacy streams at all
three rates and profiles, old-limit crossings, byte-exact short encodes, payloads
larger than 65535 bytes, malformed/oversized headers and strict final padding.
Optional WSL drivers compare all PCM with native C, check full produced counts,
and verify that the default narrow C build rejects Long. The encoder also
compares every sample of each complete output to its search model through C
before returning a file. No new AVR timing or IRQ support is claimed.
