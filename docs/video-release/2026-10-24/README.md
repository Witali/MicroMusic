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
join, technical views and ending separately. No added narration or caption
transcript was requested; retain the original Russian speech and music.

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

Publication authorization: the owner explicitly requested upload to YouTube.
The owner subsequently requested a preview before publication. Do not upload
or publish until the owner approves the finished preview.
Record the actual video URL and visibility only after Studio confirms them.

References: [FFmpeg loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm),
[YouTube upload documentation](https://support.google.com/youtube/answer/57407).
