# Soft LPC2 suggestions for the existing Q3 encoder

`tools/probe-hq4-q3-lpc2-prior.py` is an isolated offline experiment. It does
not change Q3 synthesis arithmetic or its stream format. It starts with an
explicit incumbent and keeps that exact model/PCM when no eligible improvement
is found. Original PCM, rather than synthesized LPC2 audio, remains the target.

The exact native LPC2 encoder analyzes the supplied complete 7500 Hz reference
without changing its level, DC or duration. The prior uses its decoded parameter
trajectories:

- Step down the full order-ten AR polynomial, then keep its first eight
  reflection coefficients and quantize for Q3. Truncating AR terms first would
  produce a different predictor and is not used.
- Suggest a single Q3 reflection-code step toward that prior. A shared half
  update run changes together, so this mutation does not require extra spectral
  updates. Other proposal kinds can change the actual packed byte count.
- Suggest a one-sample pitch-period step only when both current/teacher frames
  are voiced. Separate voicing proposals can change voiced/unvoiced status;
  LPC2 modes are never interpreted as Q3 pulse-shape bits.
- Suggest a one-code gain step. LPC2 residual gains and Q3 gains have different
  units; a frozen median calibration supplies only a soft envelope suggestion.

Half the proposals use those suggestions; half use the existing Q3 proposal
function. Annealing may inspect inferior working states. Exported elites must
preserve the incumbent's STOI/eSTOI, four spectral error ceilings, track
coverage, missing/extra energy, continuity and combined harmonic-loss guards.
Missing/nonfinite metrics fail. Every evaluation also checks exact signed-byte
arithmetic, wraps, output steps/peak, complete duration and actual stream bytes.
Only a lower combined spectral/track loss can replace a feasible incumbent.
The run is deliberately limited to at most 2000 proposals.

Forty-eight whole-transfer controls cross four reflection blends, four
F0/voicing policies and three gain scales. They are measured separately and
cannot silently replace the incumbent. `--control-stream-budget 602` reproduces
the historical Flash-only negative controls while allowing the actual search
more data space through EEPROM.

```text
python tools/test-hq4-q3-lpc2-prior.py
python tools/probe-hq4-q3-lpc2-prior.py --reference web-player/audio/originals/vinni.wav --model build/hq4-q3/public-vinni-t1-spectrogram/model.json --output build/hq4-q3-lpc2-prior/vinni --proposals 2000 --seed 23261 --stream-budget 639 --control-stream-budget 602 --storage eeprom-prefix --baseline-build build/hq4-q3/public-vinni-t1-spectrogram/avr/build.json --build --avr-bin C:/Work/MicroMusic/build/toolchains/avr-7.3.0/bin --node C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe
```

`flash` storage retains the original Q3/T1 capacity of 603 stream bytes and
420 code bytes (Q3 without T1: 615 and 408). `eeprom-prefix` supports T1 only:
the separately qualified floor-Q3 reader uses 448 code bytes and places the
first 64 speech bytes in EEPROM. A 639-byte stream then occupies 575 Flash
data bytes; with its EOF byte, the actual program/data total is 1024 bytes.
The Q3 numerical oracle remains unchanged. See the EEPROM builder's own
qualification and `build.json` for actual code/data/padding measurements.

With `--build`, improved Flash exports are assembled and checked in three
engines. EEPROM exports are built even for parameter fallback because that
storage layout has different reader code. Full Flash and EEPROM sizes must
pass the actual builder; an estimated size alone is not qualification.
Hardware testing and human listening remain separate, explicitly false flags.

Outputs include the exact selected model, stream, integer PCM, decoded WAV,
48-control report, search counters/history, source hashes and optional build
artifacts. `comparison.wav` alone receives a labeled common highpass/global RMS
match and peak scale; the raw decoded output is unchanged. `--retain` copies
only JSON reports/model and an optional build report, keeping generated audio,
containers and firmware out of Git. The retained Vinni study describes the
size of any actual improvement; numerical success is not a naturalness claim.
