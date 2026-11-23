# FLEURS wideband source protocol

The source-only selection was fixed before viewing any codec output. It
supplements the existing corpus with complete Russian and English utterances
having real source energy above 4 kHz and 6 kHz. No denoising, alignment, fitted
gain, trimming or reconstruction is applied to the source.

Source and license: [official Google FLEURS dataset](https://huggingface.co/datasets/google/fleurs),
CC BY 4.0, pinned revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`.
The official card and split metadata are saved locally with the acquisition
receipts. The files inspected from this revision are mono 16,000 Hz WAV FLOAT.
This is a measured asset-header rate, not a claim about microphone capture rate
or 24 kHz originals.

`acquire_fleurs.py` uses the original official per-language `audio/train.tar.gz`
and `audio/test.tar.gz` assets. It retains WAV member payloads byte-for-byte.
Prepared codec references are PCM16 WAVs at the same measured rate, with nearest
rounding only. The observed conversion error is at most half a PCM16 step and
there are no clipped prepared samples in the fixed reserve.

Selection is deterministic, independently for Russian and English:

1. Traverse the pinned official tar in its published member order.
2. Retain whole mono utterances of 4–8 seconds, with measured rate at least
   16 kHz. Use public gender-label quotas, without attempting to infer identity.
3. Require at least one source-supported fixed 1 kHz band at or above 4 kHz
   after direct 16 kHz conversion. The frozen source view uses the documented
   512-sample symmetric Hann, hop 256, padded-edge transform; support means
   more than 1e-4 of total source power. It is not a codec-output ranking.
4. Keep a bounded reserve of four train and six test utterances per language,
   balanced between the two available quota labels. The final set takes the
   first one per label from train and first two per label from test: 12 whole
   utterances total, with train used for tuning and test held out.
5. Report support at or above 6 kHz without ranking codec outcomes. All 12
   final FLEURS sources have a supported band there. Source background noise,
   breaths and fricatives remain in the originals and references.

Each compressed download is capped at 128 MiB and stops once its fixed reserve
is filled. Successful retained prefixes total 61,204,480 bytes and are marked
partial archives; they are not full-download or full-archive checksum claims.
An initial uppercase-label parsing error consumed one additional capped prefix
and selected no sources. Its observed counts and correction are recorded in an
ignored attempt receipt. Selection criteria were not changed in response to
codec results.

All media, transcriptions, identifiers, labels, hashes, per-record spectral
measurements and download receipts stay under ignored
`build/wideband-corpora/fleurs/`. The private `sources-private.json` uses schema
`lpx-native-wideband-sources-v1`; `reserve-private.json` retains the fixed reserve.
Only this reusable protocol and acquisition code are intended for tracking.

Development dependencies are NumPy, SciPy and soundfile. Run from the repository
with the existing research Python environment:

```text
python Codecs/LPX/research/v9-quality-all-2026-11-23/acquire_fleurs.py
```

Completed reserve receipts are reused; cached reruns do not redownload audio.
Source eligibility is separate from evidence that an encoder improves quality.
