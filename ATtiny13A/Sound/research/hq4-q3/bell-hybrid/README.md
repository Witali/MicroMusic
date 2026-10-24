# Q3/T1 voice with an automatically balanced bell prelude

This is a separate audition profile for the selected final bell-plus-speech
recording. It preserves all 19,328 samples: the original fitted 6,528-sample
prelude followed by the complete 12,800-sample voice. The comparison control is
the latest **balanced Q4/T1 hybrid**, retained under
`research/new-speech-naturalness/bell-hybrid-t1/balanced/`.

The wider Q3 reflection range can reproduce stronger spectral resonances than
the old Q4 lattice. The offline voice fit is retained in `../tail-voice/`.
`tools/build-q3-bell-hq4.py` accepts an explicitly tagged `hq4-q3-v1` model and
refuses Q4 data or Q3 coefficient -8. Before assembly it compares the decoded
voice against the bell model's explicitly tagged Q4/T1 control. Both STOI and
eSTOI must be preserved; fine log-spectrum error, broad spectral envelope,
unsupported energy and missing energy must not increase, and aggregate
spectrogram loss must decrease. Every intermediate byte wrap, PWM headroom and
sample-step guard also passes.

| Voice-only measurement | Balanced Q4/T1 control | Q3/T1 |
|---|---:|---:|
| STOI | .82508 | .83667 |
| eSTOI | .51995 | .55057 |
| Structural spectrogram loss | .61713 | .53836 |
| Fine log error | .64847 | .60261 |
| Broad spectral envelope | .68035 | .54859 |
| Unsupported energy | .27052 | .18696 |
| Missing energy | .26223 | .18975 |

Lower spectral distances and energy errors are better. Full-recording STOI
changes .69755 → .70493 and eSTOI .46271 → .48294. These objective improvements
do not establish an audible naturalness win. No hardware listening test or
human acceptance is claimed; public firmware is unchanged.

The three bell frequencies, phases, onset, duration, decay and original 64-byte
EEPROM sine table are preserved. An exhaustive bounded script search fits only
the three integer bell amplitudes to the reference bell/voice level relation:
6/4/3 becomes 6/5/3. The source and target bell/voice RMS ratios are included
in `quality.json`. Amplitude fitting uses the existing pipeline's raw PCM RMS
convention; listening comparisons receive a common 70-Hz highpass and global
RMS match with one shared peak scale.

## Shared multiplier and actual AVR verification

The prelude and voice share one multiplication routine. Voice coefficients now
use arithmetic `>>3`, but the bell must retain its previous `>>4` gain scale.
The new bell call therefore adds one `ASR r24` after the Q3 multiply. Since
each LUT sample times a bell gain is at most 31×7, the intermediate Q3 result
fits a signed byte and
`floor(floor(product/8)/2) = floor(product/16)` exactly. The test checks every
LUT value at all seven valid gains. Changing only the shared multiply would
incorrectly double the prelude amplitude.

The actual image uses **1,022 Flash bytes and 64 EEPROM bytes**: 576 bytes of
code, 15 bell descriptor bytes, 430 voice-stream bytes and the end marker.
The SRAM span including the stack is 30 bytes. Reference, WASM and unoptimized
WASM AVR engines reproduce all 57,984 samples exactly: one complete 19,328-sample
phrase followed by 38,656 midpoint-silence samples. There are no mismatches,
lost Timer0 events or missed samples; minimum measured timing slack is 419 CPU
cycles at 9.6 MHz. T1 output state is cleared at the bell-to-voice boundary.

The retained `model.json`, `build.json`, `quality.json` and `voice-gate.json`
fingerprint the inputs, source, actual HEX/EEPROM images and PCM. Generated
HEX, binaries, full verification traces and listening WAVs remain under
ignored `build/hq4-q3/bell-hybrid/`. The native comparison is
`comparison.wav`: original → latest balanced Q4/T1 → Q3/T1.

## Reproduce

Prepare the full reference according to the original input/excerpt provenance;
its WAV SHA-256 must be
`4914d2c349e1f2e9e102ec23949a2bb96b95b7145aa252b54a6a8341ba5ce55d`.
The builder takes the phrase boundary from the supplied bell model and does
not hardcode this recording or its timing.

```sh
python tools/test-q3-bell-hq4.py
python tools/build-q3-bell-hq4.py \
  --reference build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav \
  --bell-model ATtiny13A/Sound/research/new-speech-naturalness/bell-hybrid-t1/balanced/model.json \
  --voice-model ATtiny13A/Sound/research/hq4-q3/tail-voice/model.json \
  --output build/hq4-q3/bell-hybrid
```

Supply `--avr-bin <directory>` and `--node <executable>` if needed. This profile
has at most 432 available voice-stream bytes. A failed quality gate writes its
reasons and does not invoke the AVR toolchain.
