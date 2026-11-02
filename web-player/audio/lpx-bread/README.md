# LPX speech comparison

The 1.5 kbit/s experiment is currently omitted from the speech library while
quality work focuses on 2 and 3 kbit/s. Its assets and explicit archived links
are retained. The existing Tiny88 compact/quality comparisons below are
unchanged; they do not become real-time Tiny88 firmware. The Arduino device
has a separate [actual-firmware path](../../native/ATMEGA328P_SPEECH.md).

The user-requested phrase is retained in full: 19,200 mono samples at 8,000 Hz,
or 2.4 seconds. `original.wav` is the MP3 decoded and resampled to this reference
rate. Container metadata was removed. No trimming, time stretching or level
normalization was applied; the encoder's `auto-quiet` policy selected gain 1.

| Variant | Format | Complete encoded bytes | Actual bitrate |
| --- | --- | ---: | ---: |
| Very low rate | Experimental LPX-S15, version 8 / mode 15 | 417 | 1,390 bit/s |
| Compact | LPX v5, profile 4 | 1,008 | 3,360 bit/s |
| Higher quality | LPX v5, profile 6 with optional extra excitation | 1,899 | 6,330 bit/s |

The page also reports actual ATtiny88 Flash measurements using the explicit
SRAM512 memory profile:

| Variant | Program bytes | Encoded audio bytes | Complete test-image bytes |
| --- | ---: | ---: | ---: |
| Very low rate | 4,743 | 417 | 5,160 |
| Compact | 4,412 | 1,008 | 5,420 |
| Higher quality | 4,411 | 1,899 | 6,310 |

These are unpaced decoding test images without an audio queue or output ISR.
They reproduce every decoded PWM sample, but do not meet the 2,000-cycle
sample budget at 16 MHz / 8 kHz. They are not downloadable playback firmware.
The very-low-rate measurement uses an optional direct S15 parser; production
v5 support remains unchanged. EEPROM is unused.

The Flash HEX and EEPROM controls remain visible but disabled for these
examples. The filename link downloads the encoded `.lpx` stream.

[Direct S15 target measurement and reproduction](../../../Codecs/LPX/research/lpx-s15-2026-11-01/target_probe/README.md).

The compact and higher-quality `.lpx` files contain the existing L4HY v5
container. `low15.lpx` uses the separate experimental LPX-S15 container; it
requires its own parser and is rejected by the production v5 decoder.
Sizes include the complete
header, markers and final padding; they are audio data sizes, not firmware
Flash sizes. `manifest.json` supplies the exact values to the web page.

The decoded WAVs reproduce the native decoder's **8-bit PWM duties** as
signed PCM16 values `(duty - 128) * 256`. They contain no analog output filter.
Every sample was checked against the independent integer model and both
native common-format and v5-only C decoders, including native PWM output.
All four WAVs have the same rate and length; no playback-speed change or
transposition was used. These files provide an audio comparison; they do not establish
ATtiny88 firmware fit or real-time execution.

The S15 Python and independent C++ parsers produce byte-identical v5/P6
expansions, which are checked through the existing native common/v5-only
decoders and the independent integer model. The larger expanded reference is
not counted as the stored S15 stream. Nine bounded candidates plus three new
cadence-3 alternatives were compared under a complete 450-byte ceiling. The
417-byte incumbent had less full PCM error than the 443-byte alternatives;
no bytes were added merely to approach 1,500 bit/s.

[Experimental format, encoder and tests](../../../Codecs/LPX/research/lpx-s15-2026-11-01/README.md).

## Reproduction

From the repository root, with the existing LPX Python dependencies and native
C++ compiler available, prepare a fresh ignored output directory. Decode the
source MP3 externally supplied by the user:

```text
ffmpeg -i input.mp3 -map_metadata -1 -ac 1 -ar 8000 -c:a pcm_s16le -fflags +bitexact -flags:a +bitexact build/lpx-bread/input.wav
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py build/lpx-bread/input.wav build/lpx-bread/compact --profile 4 --refinement-calls 4
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py build/lpx-bread/input.wav build/lpx-bread/quality --profile 6 --max-bytes 1900 --refinement-calls 8
```

Use each selected `audio.l4hy`, not its raw alternative. The encoder's
`decoded.wav` is native PCM16; to reproduce the published PWM preview, apply
`standard_metrics.pwm_pcm16` to its samples and save as mono PCM16 at 8 kHz.
Run native/model parity checks before replacing published assets. Search is
bounded and these profiles do not claim globally optimal encoding.
