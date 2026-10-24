# LPC2 predictor with encoded excitation

`lpc2_excitation.py` combines the exact LPC2 Improved parameter encoder with
the retained LPX3 closed-loop excitation quantizer. It is a PC research adapter,
not an AVR implementation. Decoder code size, working memory and hardware timing
are not included in the reported data sizes.

The original files remain unchanged:

- `ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html`
- `ATmega328/Sound/reference/lpx3/hybrid_codec.py`
- `ATmega328/Sound/reference/lpx3/lpx3_decoder.js`

`tools/lpc2-reference-cli.mjs` runs the original HTML functions in Node and
exports the coefficients derived from an LPC2 file. See
[LPC2_REFERENCE_CLI.md](LPC2_REFERENCE_CLI.md) for that adapter's contract.

## API and decoding

```python
bridge = Lpc2Bridge(cache_directory)
base, metadata = bridge.encode(reference_pcm, 7500, encode_directory)
blob, pcm, information = encode_excitation(reference_pcm, 7500, base, 4, bridge)

# This independent cache has no access to the original recording.
decoder = Lpc2Bridge(empty_decode_directory)
decoded, descriptor = decode_excitation(blob, decoder)
```

`reference_pcm` is complete mono floating point PCM. Encoding does not normalize
its level, remove DC, resample, crop or transpose it. The probe requires 7500 Hz
and at least 3072 samples; the library checks that the embedded LPC2 descriptor
has the same rate and sample count. Automatic brightness correction is disabled.

Decoding requires only the complete container and the parameter-to-coefficient
implementation. No waveform, source spectrum or saved coefficient side file is
required. The bridge caches coefficients by the embedded LPC2 byte hash.

LPX3 uses the LPC2 predictor and pre-emphasis coefficient. Its excitation codes
replace the LPC2 synthetic chirp/noise excitation. The LPC2 formant postfilter
is not part of this residual decoder. Improvement from coded excitation should
not be attributed to that postfilter.

## Complete formats

Original **LPX3 version 1**, at 2, 3 or 4 bits per sample, is produced by the
original `encode_lpx3` function without changing its closed-loop loss, quantizer,
scale grid, packing or decoder. The default block length is 10 ms: 75 samples
at 7500 Hz.

The new 6 and 8 bit experiments use a distinct **LPX4 version 1** magic. They
extend the bit range using the same quantizer mathematics and scale search;
they are not upstream LPX3 profiles. The header layout is unchanged:

| Field | Bytes |
| --- | ---: |
| Magic, version, bit width, rate, sample/base counts, block size, brightness and scale count | 24 |
| Complete LPC2 base | variable |
| One scale byte per block | ceil(samples / block size) |
| Packed excitation | ceil(samples × bit width / 8) |

No size excludes the predictor parameters. `inspect_container` rejects invalid
format/width combinations, inconsistent base rate/count, noncanonical padding,
truncation and trailing bytes. Container byte counts exclude decoder code.
Any optional entropy wrapper has a separate size and decoder dependency.

The reference decoder retains its internal filter/de-emphasis limits and final
clamp to [-1, 1]. The probe reports raw input/output peak, mean, RMS and endpoint
sample counts. A zero output endpoint count does not prove there was no internal
limiting, nor that a resampled input with an overshoot was preserved exactly.

`verify_javascript` independently decodes LPX3 with the original JavaScript
decoder. For LPX4 it changes only the magic and accepted bit-width guards of
that decoder; filter and packing mathematics stay unchanged. Python and
JavaScript output must agree within 1e-6. All 120 residual outputs in the
retained four-phrase and twenty-recording study agreed bit for bit.

## Reproduce the comparison

```text
python tools/test-lpc2-excitation.py
python tools/probe-lpc2-quality.py --reference original.wav --output build/probe --bits 2 3 4 6 8 --before "Before=matching.wav"
python tools/probe-lpc2-quality.py --manifest build/speech-corpus/manifest.json --references-root build/speech-corpus --output build/corpus-lpc2 --before-hq4-root build/speech-corpus-benchmark/short/models --bits 2 3 4 6 8
```

The probe writes actual containers, unnormalized individual WAVs, a listening
sequence and JSON measurements. The sequence alone receives a common 70 Hz
highpass, global RMS matching and shared peak scaling for listening; its
processing is labeled in the report. Measurements use the raw individual PCM
except objectives that explicitly specify highpass/global level matching.
Both raw-level and level-matched strongest-partial audits are retained.

`--retain directory` copies JSON reports only. Original/derived audio and
encoded experiment containers stay in ignored build directories. Corpus
selection accepts prepared clip IDs or source clip IDs and keeps every failed
case visible in its summary. A corpus baseline must have the same reference
file hash. The short corpus comparison is 2.048 seconds per recording, with
the prepared source duration and padding left unchanged.

These measurements compare codecs at the same 7500 Hz rate. The reference
web page's default 12000 Hz configuration is a separate rate/size choice.
STOI/eSTOI and spectrogram errors support comparison, but do not establish
naturalness by themselves or guarantee quality on arbitrary voices. The
strict 5 dB audit still rejects the tested residual profiles because it also
counts missing weak selected partials. See the retained
[study](../research/lpc2-excitation/README.md) before choosing a profile.
