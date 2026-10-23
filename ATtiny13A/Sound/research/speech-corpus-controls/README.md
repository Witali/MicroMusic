# Controls accompanying the bilingual corpus

The new real-speech corpus extends the test material; the three selected
public phrases remain independent protected controls. No new codec candidate
is approved merely because the corpus-wide mean improves.

`tools/check-protected-speech.py` re-decodes the selected Tiny models for Chego
and Otvechaesh and the selected HQ4 stream for Vinni. It validates canonical
input hashes and compares complete phrase plus twice-phrase-length midpoint
silence against the exact PCM hashes in their retained three-engine AVR build
reports. All three agree. This is a fresh numerical re-decode and a comparison
to existing qualification, not a new emulator or physical-device run.

`protected-baseline.json` freezes the reference/model/PCM hashes and six
individual regression metrics. A repeat with `--baseline` rejects any changed
reference or PCM and any decline in STOI/eSTOI or increase in each of four
spectral errors. It never averages away a bad recording.

```
python tools/check-protected-speech.py \
  --baseline ATtiny13A/Sound/research/speech-corpus-controls/protected-baseline.json \
  --output build/speech-corpus-review/protected-current.json
```

The bilingual corpus originally comes from `codex/speex-avr`. An independent
check read its actual 20 input WAVs and verified every input SHA-256 against
the existing corpus manifest. `original-stress-audit.json` records additional
signal checks: both quiet cases exactly reproduce rounding of the respective
input multiplied by 10^(-24/20), with zero PCM-LSB error. Measured attenuation
is -23.9998/-23.9995 dB. Both noisy cases give approximately 15.00005 dB SNR
with no extreme-value samples. This check concerns the existing 8-kHz source
stimuli; resampling to 7.5 kHz has its own preparation report. Natural examples
use the retained 48-kHz original excerpts rather than Speex-decoded speech.

Prepared audio remains under ignored `build/`. Source attributions, exact
preparation metadata and the bilingual corpus definition are retained in
`../../test-corpus/`.
