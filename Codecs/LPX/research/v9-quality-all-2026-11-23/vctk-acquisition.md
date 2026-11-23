# Official lossless wideband source acquisition

`acquire_vctk.py` selects whole original utterances from the official
[VCTK Corpus version 0.92](https://datashare.ed.ac.uk/handle/10283/3443).
The archive contains 48 kHz, 16-bit studio recordings converted by its publisher
from the original 96 kHz recordings. The official
[license file](https://datashare.ed.ac.uk/bitstreams/956a1688-0b59-428c-8a2f-10837433dde3/download)
specifies [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
This script does not redistribute recordings, speaker metadata, transcripts or
licensing contact details. Original documents remain in its private receipt.

The 11,747,302,977-byte ZIP is not downloaded in full. A seekable HTTP reader
validates status 206 and exact `Content-Range` before consuming each archive
range. A server returning 200 is closed without reading its body. Every body
byte counts toward a persistent limit of 63 MiB, leaving space below the
study's 64 MiB ceiling for its initial one-byte capability probe and small
independent provenance checks. Cached ranges prevent duplicate transfer.

The fixed salt `lpx-native-wideband-v1` orders speaker groups and utterance
members by SHA-256. Official gender metadata, when available, produces an
alternating F/M speaker order. The bounded acquisition considers at most 48
speaker groups and 24 ordered utterances per speaker, stopping after at most
24 accepted distinct-speaker sources. FLAC STREAMINFO is checked first with a
small prefix read. Selected utterances must be mono PCM16 at 48 kHz, complete
and between four and eight seconds. The script retains the original FLAC and
an exact PCM16 WAV conversion. It applies no cropping, gain or denoising.

Eligibility depends only on the source. After direct 48-to-16 kHz conversion,
at least one 1 kHz band at or above 4 kHz must contain more than `1e-4` of total
windowed source power. The receipt records every source band, including 6–8
kHz, and any rejected upper-band candidate. Codec output is never inspected
during selection. The first four accepted sources are tuning; the remaining
ordered sources form heldout candidates and reserves. A 12-source cohort can
take the first four tuning and first eight heldout without reordering.

Run with NumPy, SciPy and SoundFile available:

```text
python acquire_vctk.py --output build/wideband-corpora/vctk-0.92 --count 24
```

The output must be inside this worktree's ignored `build/`. The private
manifest uses schema `lpx-native-wideband-sources-v1`; all source paths, audio
hashes, archive members, speaker labels, metadata, retained audio and transfer
receipts stay there. Console output contains aggregate acquisition progress
only. The script fails on an ignored range, transfer-budget exhaustion,
unexpected audio format or an insufficient deterministic reserve.
