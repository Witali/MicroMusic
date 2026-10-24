# Nearest-product rounding: diagnostic result

The retained HQ4 lattice floors its signed Q4 products. `hq4_precision.py`
tests adding 8 before the arithmetic four-bit shift, with ties toward positive
infinity. It preserves the original signed-byte negation and wrapping rules;
it is not a wider or saturating decoder. With rounding disabled it matches all
three retained HQ4 recordings exactly. Exhaustive tests cover every signed
byte and all sixteen coefficient values.

For the public Vinni stream, merely switching arithmetic reduces mean PCM
offset from 5.222 to 0.902 LSB but lowers STOI from 0.859602 to 0.828027.
The separate bounded refit below uses at most 613 stream bytes, preserving four
bytes for a possible rounding instruction pair. This is an estimated code
allowance; no rounded AVR image has been assembled or qualified.

| Public Vinni | STOI | eSTOI | Log-spectrum error | Mean signed PCM |
|---|---:|---:|---:|---:|
| Retained HQ4 | 0.859602 | 0.690986 | 0.812884 | 5.222 |
| Nearest rounding, unchanged data | 0.828027 | 0.638845 | 0.812804 | 0.902 |
| Nearest rounding, 6000 proposals | 0.847094 | 0.663353 | 0.757824 | 0.694 |

The refit improves spectral error and offset, but does not preserve either
intelligibility metric. It is retained as negative evidence and does not
replace a public recording. A zero count of jumps of at least 48 PCM LSB is
only a diagnostic threshold, not proof of naturalness. Its peak is 49 LSB.

```sh
python tools/probe-hq4-precision.py \
  --reference web-player/audio/originals/vinni.wav \
  --stream ATtiny13A/Sound/codec/release/vinni/speech.hq \
  --output build/hq4-precision/vinni --proposals 6000 --seed 23143
python tools/test-hq4-precision.py
```

`model.json` and `speech.hq` contain the exact refitted parameters. The report
retains normalized-LF source hashes, input hashes, seed and scores; the large
proposal log and generated comparisons stay in ignored `build/`. Initial
unmodified-data measurements also cover the new final phrase. Audio comparisons
use the same 70 Hz highpass, RMS matching and shared peak scale for all signals.
