# Binary voiced noise: qualified negative experiment

The full Vinni phrase is unchanged:22,272 samples at7500Hz, original SHA256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
The separate `hq4-q3-pulsebook-mixed-v1` format uses the same64 EEPROM bytes:
each byte holds coefficient+8 in its low nibble and a row-constant bit4.
The flag adds shared-LFSR noise at half gain to every voiced sample. It also
clocks at gains0/1; unvoiced samples clock exactly once and bypass the mixture.

The real assembler profiles need418/420 code bytes (floor/nearest), leaving
605/603 speech bytes in1024 Flash including EOF and alignment. This costs26
bytes more than the compact non-mixed profiles. EEPROM holds the whole table;
it cannot also hold a speech prefix.

The automatic screen compares all16 noise masks, gain scales.65/.85/1 and
three seeds; mask0 is tested only at gain1. In total138 initial trials and
1500 joint parameter/table/flag proposals use seed23419. The unchanged exact
STOI and spectrogram objectives and wrap/peak/step guards remain active.

| Full reference measurement | Compact base cycle01 | Mixed-format best |
|---|---:|---:|
| STOI | .8462036475 | .8465827282 |
| Spectrogram loss | .4932034930 | .4930415572 |
| Stream bytes |600|600|
| Actual total Flash |994|1020|
| EEPROM |64|64|
| Raw PCM mean |+.07761918|+.07719123|

**All four noise flags of the winning candidate are0.** The small metric
change therefore comes from refitting existing frame parameters, and provides
no evidence that this source extension improves speech. Keep the smaller
base profile and the existing better-STOI extended-pole candidate. The target
STOI.90 and spectrogram loss.3449755536 remains unmet. The raw DC bias is also
unresolved; the analysis highpass is not a firmware correction.

The best complete mixed image occupies1020 Flash+64 EEPROM. The actual66,816
samples (phrase followed by two phrase lengths of silence) match byte for byte
in reference, WASM and unoptimized WASM engines; no missed samples, lost timer
overflows or arithmetic wraps occur. Minimum timing slack is324 CPU cycles.
Its phrase hash is
`cd39ca8ea8a540eaab819d55f2626c9a6a849a1b6a4ed27881d556fd22285ead`.
`vinni/balanced/avr/` retains the subsequent real build/verification reports;
search reports preserve their earlier PC-only qualification flags.

Retained JSON parameters reproduce stream, table and PCM using
`codec/q3_pulsebook_mixed.py`; audio and binaries stay under ignored `build/`.
`tools/test-q3-pulsebook-mixed.py` has five oracle tests;
`tools/test-q3-pulsebook-mixed-avr.py` has five actual AVR tests including
zero-flag legacy compatibility, low-gain LFSR transitions, all modes and
maximum full images.

```sh
python tools/probe-q3-pulsebook-mixed.py \
  --reference web-player/audio/originals/vinni.wav \
  --model ATtiny13A/Sound/research/q3-core-data-cycles/vinni/cycle-01/after/model.json \
  --model ATtiny13A/Sound/research/q3-pulsebook/vinni/best_spectrum/model.json \
  --model ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json \
  --proposals 1500 --output build/q3-pulsebook-mixed/vinni
```

The search report fingerprints all sources; each seed-screen row records its input hash.
These findings do not replace any public firmware or prove a general limit
on frequency-selective mixed excitation.
