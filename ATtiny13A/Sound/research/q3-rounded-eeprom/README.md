# Rounded Q3 under the restored 1 KB requirement

The complete firmware budget is 1024 Flash bytes including code and speech,
plus 64 EEPROM bytes. The user preferred the larger six-bit excitation as an
audible quality reference, but its 16407-byte lossless container cannot serve
as a 1 KB firmware. This isolated study returns to the compact integer Q3 core.

## Actual code and storage

`hq4_q3_rounded.py` changes only multiplication from floor(product/8) to
floor((product+4)/8), ties toward positive infinity. One `ADC r24,r27` uses
the last discarded bit and the filter's existing zero register. The core grows
from 420 to 422 bytes; no public arithmetic profile is reinterpreted.

The separate EEPROM reader places the first 64 speech-stream bytes there,
including coefficient updates, pitch and gain parameters. Flash contains the
exact continuation and EOF. It reads EEPROM only; both generated HEX files
belong to the same firmware. Its 28 bytes of reader code are counted in full.

| Profile | Core | Maximum complete speech stream | Flash | EEPROM |
|---|---:|---:|---:|---:|
| Floor Q3/T1, Flash only | 420 | 603 | 1024 | 0 |
| Rounded Q3/T1, Flash only | 422 | 601 | 1024 | 0 |
| Floor Q3/T1, EEPROM prefix | 448 | 639 | 1024 | 64 |
| Rounded Q3/T1, EEPROM prefix | 450 | 637 | 1024 | 64 |

At maximum rounded size, 637 speech bytes split into 64 EEPROM and 573 Flash
bytes. The total is 450 code + 573 speech + 1 EOF = 1024 Flash bytes. This is
36 additional stream bytes compared with the same rounded Flash-only core;
the EEPROM read instructions are not treated as free space.

## Whole Vinni: not promoted

All fitting uses the unchanged complete 22272-sample, 7500 Hz original and the
frozen Q3/T1 model. A 2000-proposal run is followed by one 4000-proposal
refinement. Pitch, gain, modes, coefficients, update sharing and frame durations
remain automatically searchable through the exact decoder. The ten strongest
component trajectories and all spectral terms are evaluated on the same time
axis. No original waveform is available to the firmware.

| Measurement | Frozen Q3/T1 | Rounded, 2000 + 4000 proposals |
|---|---:|---:|
| STOI | .838396 | .830981 |
| eSTOI | .644611 | .649758 |
| Spectrogram loss | .504357 | .492822 |
| Harmonic-track loss | .927636 | .753611 |
| Mean matched-component level error, dB | 7.38 | 5.62 |
| p95 level error, dB | see baseline report | 11.38 |
| Actual Flash / EEPROM | 1024 / 0 | 1024 / 64 |

Spectral errors improve, but STOI is lower. Consequently the strict frozen
intelligibility guard rejects the candidate. Its smaller mean level error is
not an all-component 5 dB guarantee. Keep it as a listening experiment; the
separate floor-Q3 soft-prior study supplies the guarded selection.

The raw-level audit reveals a separate improvement that the RMS/highpass
spectral objective does not describe. Previous Q3 has raw mean +0.073995,
the selected floor/EEPROM variant +0.074232, while this rounded candidate has
mean -0.000227 (original -0.000059). Rounded raw RMS is 0.060649 versus
previous Q3 0.110910; raw levels are not identical. These measurements come
directly from the actual AVR samples without DC removal or normalization,
in `raw-level-comparison.json`. Reduced bias is useful but does not override
the failed STOI guard or establish subjective acceptance.

`qualified/build.json` verifies all 66816 samples (22272 phrase plus twice
that length of midpoint silence) in reference, WASM and unoptimized WASM
engines, with no mismatches, missed samples or lost timer overflows. SRAM span
including stack is 32 bytes. Minimum preparation slack is 217 cycles out of
1280. Physical hardware and subjective acceptance of this rounded variant
remain untested.

The initial compiler launch was prevented by Windows confinement. Qualification
was retried with zero proposals from the saved final model; stream bytes and
PCM were checked to remain identical. The qualified report includes final
source hashes and actual build measurements. Partial search reports retain
their honest `avr_assembled: false` flags; only `qualified/` is AVR qualified.

## Reproduction

Run in the project Python environment with NumPy, SciPy, SoundFile, Numba and
the speech metrics installed:

```powershell
python tools/probe-q3-rounded-1kb.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --output build/q3-rounded-1kb/initial --proposals 2000 --seed 23273 --stream-budget 637 --eeprom
python tools/probe-q3-rounded-1kb.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --resume-model build/q3-rounded-1kb/initial/model.json --output build/q3-rounded-1kb/refined --proposals 4000 --seed 23274 --stream-budget 637 --eeprom --build --avr-bin <avr-bin> --node <node>
python tools/probe-q3-rounded-1kb.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --resume-model ATtiny13A/Sound/research/q3-rounded-eeprom/refine-4000/model.json --output build/q3-rounded-1kb/qualified --proposals 0 --seed 23274 --stream-budget 637 --eeprom --build --avr-bin <avr-bin> --node <node>
```

Only JSON models/reports and compressed speech source bytes are retained here.
Generated audio, ELF, HEX and binary firmware remain in ignored build output.
The separately retained protected examples still pass unchanged PCM and metric
checks. Boundary tests exercise extended headers at byte 63, coefficients
crossing byte 64, Flash-first EOF and both exact maximum-size profiles.
