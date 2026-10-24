# MicroMusic site walkthrough, 24 October 2026

An original four-second title card precedes two owner-supplied phone recordings
in filename order, complete and without re-encoding the original footage.
`create_intro.py` draws the title card using Pillow and encodes it with FFmpeg.
Retain the originals outside this repository.
`source.json` records the inputs and first-pass FFmpeg loudnorm measurements.
`render.py` creates individually normalized PCM audio, joins it sample-exactly,
and muxes the original H.264 video with 48 kHz stereo AAC at 256 kb/s.
Loudness target: -16 LUFS, true-peak target -1.5 dBTP before AAC. The 50 LU LRA
ceiling avoids requesting unnecessary dynamic-range compression; the peak
limiter still operates because the source peaks prevent a simple gain increase.
AAC can slightly increase true peaks; verification measures the encoded result.

Output: `C:/Work/YouTube Videos/MicroMusic/`. Supporting audio, source probes,
hashes, timeline and logs go into `materials/work/`. Editable source snapshots
go into `materials/project/`; this Git directory remains canonical. No MIDI
source files or video binaries belong in this repository.

Run with Python 3.11+ and FFmpeg/ffprobe on PATH:

```powershell
python render.py
python verify_video.py 'C:/Work/YouTube Videos/MicroMusic/MicroMusic-1KB-2026-10-24-preview.mp4' --timeline 'C:/Work/YouTube Videos/MicroMusic/materials/work/timeline.json' --reference-audio 'C:/Work/YouTube Videos/MicroMusic/materials/work/soundtrack-normalized.wav' --report 'C:/Work/YouTube Videos/MicroMusic/materials/work/verification.json'
```

Run `python create_intro.py` before rendering. The verifier needs NumPy.
It checks original decoded frame hashes, frame counts,
complete decoding, timestamps, chapters, duration, Russian audio metadata,
per-part AAC loudness and correlation with the normalized PCM reference. The
phone footage has variable frame timing, retained exactly, so a generated-film
constant-frame-rate invariant would be inappropriate. Inspect final opening,
join, technical views and ending separately. Retain the original Russian speech
and music. No added narration is included.

The YouTube title and Russian description accompany the file. The 1 KB headline
refers specifically to ATtiny13A Flash, as the description explains. Source
sizes are documented in the project README and firmware build reports. Site
links come from this repository and the previous Z80 release package.

The reviewed intro uses a stylized SOP-8 package with four leads per side and
a pin-1 marker. The 13:11 base preview passed verification: 23,738 decoded
frames, including all 23,618 original frames; 1920 x 1080; -16.08 LUFS overall;
individual recordings -16.17 and -16.03 LUFS. Encoded AAC true peak: -1.15 dBTP
(the pre-AAC target was -1.5). Source identities and the measured verification
receipt are retained beside this document. No original footage is re-encoded.

## English subtitles

The owner subsequently requested English subtitles or an additional Microsoft
Jenny audio track. This revision provides subtitles and retains Russian audio.
`transcribe.py` runs faster-whisper 1.2.1 locally with the multilingual small
model, revision `536b0662742c02347bc0e980a01041f333bce120`, CPU int8 and Russian
word timestamps. Package wheels and hashes are recorded in the local
`build/video-asr-install-report.json`; model weights remain outside Git.
Original speech is not sent to a transcription service.

`subtitles-English.json` is the reviewed translation: 105 cues split at actual
spoken phrases, with project and chip names corrected against repository files.
It subtitles the commentary; instrumental music is left uncaptained. Some
distorted demonstration voice samples are not intelligible in the automatic
transcript. The translation does not invent their missing words.

Run `python add_subtitles.py` after the base render. This exports the standalone
UTF-8 `MicroMusic-English.srt` and a selectable English `mov_text` track in
`MicroMusic-1KB-2026-10-24-preview-en-subs.mp4`. It verifies cue ordering, bounds,
maximum two lines of 42 characters, reading speed and exact SRT round-trip.
It also compares encoded video/audio stream SHA-256 values with the completely
verified base film, proving the subtitle remux preserved both media streams.
YouTube Studio needs the separate SRT uploaded with timing; embedded MP4 text
does not replace that step. A small burned-caption preview may be generated for
players that cannot display MP4 subtitle tracks.

Sources: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[model](https://huggingface.co/Systran/faster-whisper-small),
[YouTube captions](https://support.google.com/youtube/answer/2734796).

Publication authorization: the owner explicitly requested upload to YouTube.
The owner subsequently requested a preview before publication. Do not upload
or publish until the owner approves the finished preview.
Record the actual video URL and visibility only after Studio confirms them.

References: [FFmpeg loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm),
[YouTube upload documentation](https://support.google.com/youtube/answer/57407).
