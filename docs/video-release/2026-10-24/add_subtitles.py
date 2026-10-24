"""Validate reviewed English cues, export SRT and mux a selectable MP4 track."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('C:/Work/YouTube Videos/MicroMusic')
HERE = Path(__file__).resolve().parent
WORK = ROOT / 'materials' / 'work'
BASE = ROOT / 'MicroMusic-1KB-2026-10-24-preview.mp4'
OUTPUT = ROOT / 'MicroMusic-1KB-2026-10-24-preview-en-subs.mp4'
cues = json.loads((HERE / 'subtitles-English.json').read_text(encoding='utf-8'))['cues']
plan = json.loads((WORK / 'timeline.json').read_text(encoding='utf-8'))


def timestamp(seconds):
    value = round(seconds * 1000)
    return f'{value // 3600000:02}:{value // 60000 % 60:02}:{value // 1000 % 60:02},{value % 1000:03}'


previous_end = 0
for start, end, text in cues:
    assert previous_end <= start < end <= plan['duration'], (start, end)
    assert text.strip() and len(text.splitlines()) <= 2
    assert max(map(len, text.splitlines())) <= 42, text
    assert len(text.replace('\n', '')) / (end - start) <= 23, text
    assert end - start <= 12, (start, end)
    previous_end = end
srt_text = ''.join(f'{i}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n\n'
                   for i, (start, end, text) in enumerate(cues, 1)).rstrip() + '\n'
srt = ROOT / 'MicroMusic-English.srt'
srt.write_text(srt_text, encoding='utf-8')
(HERE / 'MicroMusic-English.srt').write_text(srt_text, encoding='utf-8')
command = ['ffmpeg', '-y', '-hide_banner', '-nostats', '-i', str(BASE), '-i',
           str(srt), '-map', '0:v:0', '-map', '0:a:0', '-map', '1:0',
           '-map_metadata', '0', '-map_chapters', '0', '-c:v', 'copy', '-c:a',
           'copy', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
           '-metadata:s:s:0', 'title=English', '-disposition:s:0', 'default',
           '-movflags', '+faststart', str(OUTPUT)]
result = subprocess.run(command, capture_output=True)
(WORK / 'subtitles-mux.log').write_bytes(result.stderr)
result.check_returncode()


def stream_hashes(path):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map',
                             '0:v:0', '-map', '0:a:0', '-c', 'copy', '-f',
                             'streamhash', '-hash', 'sha256', '-'],
                            capture_output=True, check=True)
    assert not result.stderr.strip(), result.stderr.decode(errors='replace')
    return result.stdout.decode().strip()


assert stream_hashes(BASE) == stream_hashes(OUTPUT), 'Original encoded video/audio changed'
info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams',
                                 '-show_format', '-of', 'json', str(OUTPUT)],
                                capture_output=True, check=True).stdout)
assert any(s['codec_type'] == 'subtitle' and s['tags']['language'] == 'eng'
           for s in info['streams'])
assert abs(float(info['format']['duration']) - plan['duration']) < 0.12
extracted = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(OUTPUT),
                            '-map', '0:s:0', '-c:s', 'srt', '-f', 'srt', '-'],
                           capture_output=True, check=True).stdout.decode('utf-8-sig')
assert extracted.replace('\r\n', '\n').strip() == srt_text.strip()
plan['output'] = str(OUTPUT)
plan['subtitle_file'] = str(srt)
plan['subtitle_cues'] = len(cues)
(WORK / 'timeline-subtitled.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
with OUTPUT.open('rb') as stream:
    checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
receipt = dict(file=str(OUTPUT), cues=len(cues), language='eng',
               sha256=checksum, srt_roundtrip='passed',
               original_video_and_audio_stream_hashes='match verified base preview',
               verified_base_sha256=json.loads((WORK / 'verification.json').read_text())['sha256'])
(WORK / 'subtitle-verification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, indent=2))

# A compact preview with visible captions also works in players that do not
# expose embedded mov_text tracks. The full film retains selectable captions.
preview = ROOT / 'MicroMusic-English-caption-preview.mp4'
filters = "scale=960:-2,subtitles=MicroMusic-English.srt:force_style='FontName=Segoe UI,FontSize=18,Outline=1.5,Shadow=0'"
result = subprocess.run(['ffmpeg', '-y', '-hide_banner', '-nostats', '-i', str(BASE),
                         '-t', '45', '-vf', filters, '-r', '30', '-c:v', 'libx264',
                         '-preset', 'fast', '-crf', '21', '-c:a', 'aac', '-b:a',
                         '128k', '-movflags', '+faststart', str(preview)],
                        cwd=ROOT, capture_output=True)
(WORK / 'caption-preview.log').write_bytes(result.stderr)
result.check_returncode()
print(f'Caption preview: {preview}')
