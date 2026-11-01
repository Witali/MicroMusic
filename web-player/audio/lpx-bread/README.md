# LPX speech comparison

The user-requested phrase is retained in full: 19,200 mono samples at 8,000 Hz,
or 2.4 seconds. `original.wav` is the MP3 decoded and resampled to this reference
rate. Container metadata was removed. No trimming, time stretching or level
normalization was applied; the encoder's `auto-quiet` policy selected gain 1.

| Variant | Format | Complete encoded bytes | Actual bitrate |
| --- | --- | ---: | ---: |
| Compact | LPX v5, profile 4 | 1,008 | 3,360 bit/s |
| Higher quality | LPX v5, profile 6 with optional extra excitation | 1,899 | 6,330 bit/s |

Both `.lpx` files contain the existing L4HY v5 container. Sizes include its
header, markers and final padding; they are audio data sizes, not firmware
Flash sizes. `manifest.json` supplies the exact values to the web page.

The two decoded WAVs reproduce the native decoder's **8-bit PWM duties** as
signed PCM16 values `(duty - 128) * 256`. They contain no analog output filter.
Every sample was checked against the independent integer model and both
native common-format and v5-only C decoders, including native PWM output.
All three WAVs have the same rate and length, so playback preserves pitch and
duration. These files provide an audio comparison; they do not establish
ATtiny88 firmware fit or real-time execution.

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
