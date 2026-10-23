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

## Prepared references and listening

`prepared-audit.json` independently checks all 40 final reference WAVs against
resampling of the selected upstream original, float32 storage, the declared
crop and trailing zero padding. All saved PCM agrees exactly. The final
manifest SHA identifies the preparation being audited. Speaker sets for
tuning and evaluation are disjoint. One full excerpt and its short window
retain a 1.013 peak from resampling; this is explicitly reported rather than
silently clipped or normalized.

`reference-properties.json` measures the first short natural excerpt from
each of the eight speakers with the same generic source analysis used for
the earlier character voices. Estimated median F0 ranges from about 78 to
243 Hz. These values are analysis estimates with possible octave errors,
not annotated pitch ground truth. The corpus extends testing toward low
natural voices and different amounts of aperiodic speech; the already good
high cartoon voices remain separate controls.

The ignored local gallery contains all 20 short originals and the automatic
HQ4 baseline outputs, including quiet/noisy variants. It preserves their raw
level relationships and displays source credits and the unqualified Flash
estimate. The baseline has zero search proposals and must not be described
as the best quality attainable by HQ4.

```
python tools/make-speech-corpus-player.py \
  --manifest build/speech-corpus/manifest.json \
  --references-root build/speech-corpus \
  --benchmark build/speech-corpus-benchmark/short/report.json \
  --output build/speech-corpus-listen
```

Serve the development checkout and open `build/speech-corpus-listen/`.
The gallery copies generated WAVs only into ignored build output. No speech
recordings or derived PCM are added to Git.
