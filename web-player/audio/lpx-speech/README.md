# Shared LPX speech

The three original Tiny13 phrases have LPX v5 profile 4 and 6 equivalents here.
`manifest.json` pins their public sources, exact sample counts, byte costs and
encoder sources. The fourth phrase retains `../lpx-bread/` byte-for-byte.

Rebuild with `python tools/prepare-shared-speech.py --retain` from the repository
root, with the existing codec Python dependencies and native C++ compiler.
The script resamples 7500 → 8000 Hz without trimming, speed change or gain,
then checks every stream through the integer model and common/v5-only decoders.
WAV previews store exact PWM8 as signed PCM16 `(duty - 128) * 256`.

[Every file and its compression recipe](../../../docs/speech-assets.md).
