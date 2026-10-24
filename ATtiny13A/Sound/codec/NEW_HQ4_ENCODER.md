# New recordings in the original HQ4 format

`new_hq4_encoder.py` initializes previously unseen recordings automatically. It
uses the unchanged 406-byte signed eight-bit lattice, its eight Q4 reflection
coefficients, four excitation profiles and 64/128/192/256-sample frames. This
keeps code plus stream plus the end marker within 1024 bytes of Flash; it does
not use EEPROM. Final HEX still needs independent AVR-emulator verification.

Prepare the full recording as mono 7500-Hz PCM, pad its end to a multiple of 64,
and pass its WAV from an external or ignored build directory. The encoder does
not trim, accelerate or transpose input audio. Record preprocessing and source
hashes separately. For example, from the repository root:

```sh
python tools/encode-new-hq4.py --reference build/input/reference.wav \
  --output build/new-hq4/example --proposals 5000 --seed 23105
```

`--stream-budget` selects a tighter compressed-data limit, from 8 to 617 bytes.
`--initial-model` continues optimization from an exported `model.json` and checks
the prepared reference hash. The random seed makes each search repeatable.

Initialization compares analysis grids at 64, 128 and 256 samples, regularized
LPC with two Q4 quantization initializers, optional pre-emphasis, local normalized
autocorrelation pitch candidates, relative-energy gains and automatic sharing
of similar spectral halves. Candidate selection decodes every feasible stream
with the exact integer model. Search then adjusts coefficients, pitch, gain,
excitation, frame boundaries and frame splits/merges under the byte budget.
No manually marked phonemes, speaker frequencies or recording-specific time
regions are used.

New phrases have no archived quality floor. Their elite must retain the initial
STOI, remain below a three-percent spectral-loss ceiling and improve
`STOI - 0.08 * spectral_loss`. Spectral loss is the existing common-70-Hz-highpass,
RMS-matched 128/256/512-point STFT objective. Peak magnitude must stay at most
115 signed PWM units, with no adjacent step of 48 units or more. These proxies
do not establish naturalness or human intelligibility; listen to the exported
level-matched original/result comparison before selecting a public example.
The final report includes deterministic eSTOI, exact PCM/stream hashes,
normalized-source hashes, runtime versions, initialization settings and search
history. `model.json` and `speech.hq` reproduce the selected parameters.

The format itself cannot represent arbitrarily long phrases in 1 KiB. Even
with all coefficients shared and every pitch fitting a short header, it needs
at least `2 * ceil(samples/256) + 4` stream bytes. A 126144-sample recording
therefore needs at least 990 stream bytes before the 406-byte decoder and end
marker. Such input is rejected explicitly; making it fit requires a different
duration format, lower output sample rate, or a larger memory budget.

Run `python tools/test-new-hq4-encoder.py` for period, full-length, rate-bound,
exact round-trip, deterministic-search and invalid-input checks.
