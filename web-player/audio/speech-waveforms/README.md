# Complete speech waveforms from retained firmware

`tools/build-speech-waveforms.mjs` executes the selected Flash and EEPROM from
`web-player/hq4-firmware.json` and `web-player/firmware-attiny13a-speech-extra.json`
in the reference AVR core. It captures every declared sample with active IRQ
and rejects lost overflows or samples. No original recording substitutes for
firmware output, and this step does not encode or compress speech.

Each mono 7500 Hz WAV stores exact PWM duties as PCM16 `(duty - 128) * 256`.
`manifest.json` records the entry ID, Flash/EEPROM hashes, sample count and
both PWM and WAV SHA-256 hashes. Regenerate after changing a selected image:

```text
node tools/build-speech-waveforms.mjs
```

The speech page's signal-view selector chooses the full phrase or the current
85 ms window without restarting playback. `lib/speech-waveform.js` reuses the
player's existing Renderer resampling/filter code for full Tiny input/output
views at the current filter and volume settings. Tiny audio still comes from
executing the firmware. LPX uses its exact native-decoder WAV for the same
views. Physical analog output is not measured by these artifacts.

[Every waveform and its source/recipe](../../../docs/speech-assets.md).
