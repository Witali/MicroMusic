# Final-phrase waveform naturalness experiments

These experiments investigate alternatives after the HQ4 voice was heard as
too buzzy. Objective scores are diagnostics, not proof of naturalness. No
public firmware selection changes are made here.

The input is the final phrase selected from `vhodit-i-vyhodit.mp3`, with the
bell treated separately. The source MP3 SHA-256 is recorded in the imported
input manifest. The selected complete tail is 19328 samples at 7500 Hz,
SHA-256 `4914d2c349e1f2e9e102ec23949a2bb96b95b7145aa252b54a6a8341ba5ce55d`.
For this voice study only, its first 6528 samples are excluded: voice input is
exactly `tail[6528:]`, 12800 samples, with no additional amplitude adjustment.
WAV SHA-256 is
`e725be54dc17ba77051002b20c3dd825560e2554f49e70c20628c89fecea0c0c`.

## Results

All metrics below cover the same 12800 speech samples. Log spectral error
uses the existing 70 Hz highpass and RMS-matched multiresolution objective.

| Variant | STOI | eSTOI | Log spectral error | Size qualification |
| --- | ---: | ---: | ---: | --- |
| HQ4 voice before this experiment | 0.788595 | 0.449841 | 0.855293 | Separate hybrid firmware baseline |
| Integer eight-wave initialization | 0.604278 | — | 1.017624 | 714 code + 308 data, 64 EEPROM |
| Integer eight-wave unconstrained search | 0.761788 | — | 0.946754 | 1086 Flash + 64 EEPROM; oversized |
| Integer eight-wave hard-budget search | 0.695288 | — | 0.962716 | Measured 1024 Flash + 64 EEPROM; not AVR qualified in this study |
| Full period / learned colored residual | 0.807296 | 0.472105 | 0.795115 | **834 bytes of data only; executable decoder excluded** |

The integer run uses 6000 proposals total, split into two 3000-proposal
searches. The colored experiment uses 500 residual, 2000 joint frame and 2000
waveform-book proposals. Its byte payload, model and decoded floating PCM
were reproduced exactly by a second complete run. Packing and independent
unpacking preserve decoded PCM exactly.

The colored model is a PC research candidate. Its data already occupy 834
bytes, leaving only 190 bytes of a 1024-byte image for a decoder. The existing
tiny decoder requires at least 694 bytes and does not implement this colored
model. This result therefore does **not** demonstrate an ATtiny13 firmware
fit. It also excludes the bell. A bell-plus-voice executable would need its
own separate size and cycle qualification.

## What the comparison establishes

The strong earlier Chego Tiny result was reduced from an already trained
Fixed16 model at STOI 0.921, rather than from this new generic initializer.
Short direct training of a small dictionary does not reproduce that starting
quality. On the current voice, the full learned period/noise route improves
the objective scores over HQ4, whereas the directly trained 1 KB integer
version still falls short.

Legacy pitch analysis classifies 73 of 200 voice frames as voiced; estimated
voiced F0 has 5th/50th/95th percentiles about 107/185/745 Hz. The strict
voice-priority mode accepts only 33 frames and is not promoted. These counts
are estimates, not measured pitch ground truth. They suggest checking pitch,
phase and aperiodic components together before blaming dictionary size.

## Reproduction

Prepare the same selected tail using the retained input/extraction tools,
then write its exact slice `[6528:]` as PCM16 WAV. Confirm the hash above.
The default search seeds and parameters are retained in the reports.

```
python tools/encode-new-tiny-speech.py \
  --reference build/new-speech/bell-hybrid/voice-reference.wav \
  --output build/new-speech/tiny-naturalness/voice-only \
  --avr-bin build/toolchains/avr-7.3.0/bin --proposals 6000 --starts 8

python tools/probe-new-period-voice.py \
  --reference build/new-speech/bell-hybrid/voice-reference.wav \
  --baseline build/new-speech/bell-hybrid/voice/decoded.wav \
  --output build/new-speech/tiny-naturalness/colored-voice-repro
```

The latter listening sequence is **Original → Baseline HQ4 → Original →
Colored period model**. `colored.wav` is the matched listening version;
`decoded.wav` is the raw floating decoder output. Generated WAVs and payloads
stay under ignored `build/`. Selected source models and their full reports
are retained in `final-voice/` with normalized source fingerprints.

The next useful waveform step is co-training a full model and then reducing
it through the exact integer decoder while retaining both spectral and
intelligibility limits. No naturalness claim should be made without listening
to the matched results, and no AVR claim without a complete linked build and
cycle-accurate verification.
