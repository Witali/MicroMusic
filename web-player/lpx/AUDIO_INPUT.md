# Bounded local source decoding

MP3 (MPEG1/2/2.5 LayerIII), AAC-LC/ADTS, ordinary unencrypted AAC M4A/MP4,
and mono/stereo PCM16 RIFF WAV are range-read in the dedicated encoder Worker.
The application does not create a complete AudioBuffer for these formats.
Other browser-supported formats retain the existing whole-file Web Audio path.
Unsupported WAV encodings, encrypted/fragmented MP4 and ambiguous/malformed
sample tables fail explicitly; there is no hidden whole-file fallback.

`m4a-demux.js` supports early/late moov, 32/64-bit offsets and edit trimming.
`audio-demux.js` handles MP3 ID3/Xing/LAME delay/padding and ADTS packet clocks.
MP4 metadata is capped at16 MiB, packet count at2 million, packet size at1 MiB
and cached range reads at64 KiB. Metadata indexing is proportional to packet
count within those limits; decoded PCM memory is not proportional to duration.
All offsets, packet coverage, media bounds and timeline lengths are checked.

The Worker feature-checks `AudioDecoder.isConfigSupported`. AAC/MP3 support is
browser/platform dependent; unsupported configurations produce a clear error.
At most eight compressed chunks are queued. AudioData is copied in4096-frame
portions and promptly closed. Queue backpressure uses dequeue events; flush
occurs only at actual EOF. Intermediate flushes were rejected after real browser
comparisons exposed lost AAC overlap/MP3 synthesis history.

Downmixing, rational-phase windowed-sinc resampling and PCM16 conversion run in
one portable C++ module shared by native/WASM checks. It has fixed1 MiB memory,
no imports, and carries FIR/rational phase across packet boundaries. It supports
the common7.35–96 kHz rates enumerated in source and outputs8/12/16 kHz mono.
Its passband differs from Web Audio's built-in resampler. Browser decoder
comparisons therefore use Web Audio at the source rate followed by the same
FIR, with no gain/delay fitting; FIR response is tested separately.

## Local temporary storage and cancellation

Prepared PCM is written to an origin-private temporary file with a random name
unrelated to the selected source. The encoder reads at most20528 samples at a
time. Whole-file loudness is measured once and one constant bounded gain is
applied before encoding; it remains optional and off by default. Verification
PCM occupies separate regions of the same temporary file, and the final LPX
is independently decoded through a20480-sample window and compared sample by
sample. Only the compressed output remains in browser memory.

Success/errors close and delete the temporary file. Cancellation terminates the
Worker and removes its known file with bounded retries. Startup recovery removes
only app-owned random files whose per-file WebLock is free, preserving live
jobs and unrelated origin files. Quota errors report the local storage problem.
A crash may leave temporary data until the next page load; clearing this site's
browser data removes it. No source, PCM, metadata or filenames are uploaded.

The100 MiB input limit remains. Fast accuracy streaming accepts64 million
output samples; full search and streaming refinement accept32 million. The
default16 kHz rate preserves source partials below8 kHz, whereas8 kHz removes
everything above4 kHz before compression. Explicit
full search loads whole prepared PCM into WASM; refined whole-output quality
admission can also require whole-file buffers. The fast window path avoids
those buffers. This is bounded source decoding, not a claim that every optional
quality search has constant memory. One continuous V9/Long output carries all
codec history; it is never a concatenation of independently reset files.

## Validation and references

Unit/native checks cover demux corruption, exact edits/packet clocks, arbitrary
FIR packet boundaries, response at1/2.9 kHz and7 kHz alias rejection, fixed memory,
native/WASM equality, decoder lifetime/EOF/backpressure, OPFS region separation,
quota cleanup and lock-aware crash recovery. Browser comparisons on changing
chirp/tone/transient fixtures pass for MP3 with/without Xing, M4A, ADTS and WAV.
MP3/AAC outputs match source-rate Web Audio followed by the same FIR exactly;
PCM16 WAV differs by at most one PCM16 LSB due to Web Audio input scaling.

Long recording validation also completed through the actual UI fast path as
one V9 Long file with complete sample/EOF verification. Private media, titles,
durations, paths and per-recording results are excluded from this distribution.

The protocol follows the [W3C WebCodecs processing model](https://www.w3.org/TR/webcodecs/)
and [WHATWG origin-private file system](https://fs.spec.whatwg.org/). Codec
support is queried at runtime; the specifications do not require every codec.
No runtime decoder, native toolchain or Python dependency is downloaded.
