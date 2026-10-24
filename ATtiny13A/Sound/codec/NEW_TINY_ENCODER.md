# Encoding an additional recording for the tiny decoder

`tools/encode-new-tiny-speech.py` accepts an arbitrary mono 7500 Hz WAV. It
learns the phase trajectory, waveform dictionary, gains and white residual
levels automatically. Existing canonical examples and their hash contracts
are unchanged. The new encoder emits the existing `period-fixed-v1` model;
the AVR synthesis arithmetic and firmware source are unchanged.

```
python tools/encode-new-tiny-speech.py \
  --reference build/new-speech/input/example/reference.wav \
  --output build/new-speech/tiny/example \
  --avr-bin build/toolchains/avr-7.3.0/bin --proposals 3000
```

The tool tests dictionaries of 1, 2, 4 and 8 waveform periods. It measures each
decoder specialization with the actual AVR compiler before choosing the
remaining Flash budget. EEPROM holds at most 64 bytes of waveform data.
Power-of-two gain modes avoid adding the optional 3/4 gain implementation.
White residual levels are initialized using the power of the decoder's actual
integer noise source. Pitch, waveform, gain and residual remain automatically
retunable through the existing exact integer `TinySearch` implementation.

Automatic regional holding tests several temporal resolutions for the wave,
gain and noise fields. Pitch candidates either preserve the original integer
phase-increment sum or use the nearest regional mean. Candidates are scored on
the entire recording; no manually chosen phonemes, speaker frequencies, silence
cuts or time compression are applied. Only a final partial 64-sample block is
zero-padded. `quality.json` records the original and padded sample counts.

Two models are retained: `quality-model.json` minimizes the balanced speech and
spectral objective without a Flash constraint; `fit-model.json`, when present,
obeys the measured code-plus-data limit. The total proposal budget is split
between these two exact integer searches. `quality.wav`, `fit.wav`,
`original.wav` and `comparison.wav` use the same listening-level treatment.
Waveform similarity and STOI are diagnostics; a size fit does not establish
acceptable subjective quality.

The current tiny format permits at most 1023 complete 64-sample blocks, about
8.73 seconds at 7500 Hz. Longer input is rejected explicitly. Changing that
limit requires a separate decoder/format change. A final AVR build is still
required to establish linked image size, SRAM/stack use, cycle deadlines and
matching PCM in all three emulation engines:

```
python tools/build-tiny-speech.py --model build/new-speech/tiny/example/fit-model.json \
  --output build/new-speech/tiny/example/avr --avr-bin build/toolchains/avr-7.3.0/bin \
  --play-once
```

The encoder reports `avr_verified: false` until that independent build. All
generated candidates and audio belong under ignored `build/`; retain only
selected source models and their reproducible research reports in Git.
