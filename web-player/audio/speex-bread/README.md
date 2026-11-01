# Speex versions of the shared speech phrase

These are two derivatives of the existing public
[`original.wav`](../lpx-bread/original.wav): mono PCM16, 8 kHz,
19,200 samples, 2.4 seconds. There is no resampling, gain adjustment,
time stretching, or substituted voice.

| Variant | NB mode | Nominal codec rate | Stored packet | Packets | Raw file | Actual stored rate over 2.4 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compact | 1 | 2,150 bit/s | 6 bytes | 121 | 726 bytes | 2,420 bit/s |
| quality | 3 | 8,000 bit/s | 20 bytes | 121 | 2,420 bytes | 8,066.6667 bit/s |

Mode 1 uses 43 meaningful bits per frame, stored in 48 bits. Its five
byte-padding bits and the final flush frame count towards the actual rate.
Mode 3 uses all 160 bits in its 20-byte packet. The compact example is a
deliberately low-rate, vocoder-like comparison; no equivalent-quality claim
is made.

Each `.spxraw` file is the complete concatenation of fixed-size NB packets,
without Ogg headers, comments, or other metadata. Use the manifest's mode,
packet size, and trimming information to decode it.

The previews are produced by the project's **native C decoder**, with NB1
enabled and assembly disabled. Each full decoded PCM16 stream was checked
byte-for-byte against a separate decoder compiled from the untouched,
pinned Xiph Speex 1.2.1 source. Decoder enhancement and highpass are disabled
in both paths. The target decoder project is ATmega328P; these files provide
no ATtiny88 firmware, program-Flash measurement, or target timing result.

## Delay and full-phrase retention

The encoder's reported lookahead is 40 samples; the reference decoder's
runtime lookahead is another 40. One 160-sample zero frame is appended to
the original PCM before encoding. All 121 packets, including the flush
packet, are retained. Full native decoding returns 19,360 samples.

The previews remove 80 samples at the beginning and 80 at the end, preserving
19,200 samples. FFmpeg's first packet timestamp is -40, its last is 19,160,
and the final Ogg granule is 19,320: encoder-input length minus encoder
lookahead. That container granule does not change the raw decoded length.

PWM duty is exactly `(s16 >> 8) + 128` after trimming. Each preview WAV stores
`(duty - 128) * 256` as mono PCM16 at 8 kHz, so only 256 amplitude levels
occur. Each WAV is 38,444 bytes: a 44-byte PCM header and 38,400 bytes of data,
with no metadata chunks.

## Reproduction

Run from the repository root with Python 3, a Clang/GCC-compatible native
C compiler, and FFmpeg/FFprobe with `libspeex` available:

```sh
python web-player/audio/speex-bread/prepare.py --cc clang --build-dir build/speex-bread-reproduction
```

The output directory must be new and inside the repository's ignored
`build/`. The script verifies pinned upstream/import sources and invokes
the existing source preparation tools; it does not download anything or
change tracked codec code. It writes generated streams, WAVs, manifest,
native binaries, logs, source hashes, and verification evidence there.
Existing public artifacts are compared without overwriting them. The
optional `--publish` switch copies only to absent public destinations.

The published encoding used FFmpeg 8.1.1 with Speex header version 1.2.1,
CBR 2,150/8,000 bit/s, complexity 3, VBR/ABR/VAD/DTX disabled, one frame per
packet, and the encoder's default highpass. Input is explicit little-endian
PCM16 at 8 kHz, mono, followed by 160 zero samples. Decoder builds use C11,
`-O2 -fwrapv -fno-strict-aliasing` and the existing fixed-point source recipes.
The ignored receipt retains the exact tool and source identities.

The compact encoding was completed in an earlier preparation attempt and
reused unchanged after correcting a final-granule assertion. The quality
encoding and both complete native comparisons then finished successfully.
The final script subsequently received only an output-routing change so
reproduction in a checkout containing the public assets stays usable.

Primary references: the [Speex NB framing and bit allocation](https://www.speex.org/docs/manual/speex-manual/node10.html),
the [Speex decoder API and enhancement control](https://www.speex.org/docs/manual/speex-manual/node7.html),
and [FFmpeg's libspeex encoder](https://ffmpeg.org/doxygen/8.0/libspeexenc_8c_source.html).
The existing vendored source's license and provenance remain in
`Codecs/Speex/AVR/vendor/speex-1.2.1/`; no upstream implementation is copied
into this asset folder.
