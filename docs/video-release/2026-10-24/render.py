"""Join the original phone recordings and normalize each recording's audio."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def run(args, log=None):
    result = subprocess.run(args, capture_output=True)
    if log:
        log.write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format',
                           '-show_streams', '-of', 'json', str(path)]))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('source.json'))
    args = parser.parse_args()
    plan = json.loads(args.source.read_text(encoding='utf-8'))
    root = Path(plan['output_directory'])
    work = root / 'materials' / 'work'
    work.mkdir(parents=True, exist_ok=True)
    audio = plan['audio']
    rate = audio['sample_rate']
    entries = []
    for source in plan['sources']:
        path = Path(source['path'])
        info = probe(path)
        sound = next(s for s in info['streams'] if s['codec_type'] == 'audio')
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        duration = float(info['format']['duration'])
        samples = round(duration * rate)
        measured = source.get('measurement')
        filters = (
            f"loudnorm=I={audio['integrated_lufs']}:TP={audio['true_peak_dbtp']}:"
            f"LRA={audio['lra_ceiling']}:measured_I={measured['input_i']}:"
            f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
            f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:"
            f"linear=false:print_format=json,aresample={rate},apad=whole_len={samples},"
            f"atrim=end_sample={samples},asetpts=PTS-STARTPTS"
        ) if measured else f'aresample={rate},apad=whole_len={samples},atrim=end_sample={samples},asetpts=PTS-STARTPTS'
        wav = work / f"{source['id']}-normalized.wav"
        print(f"Normalizing {source['id']}: {duration:.3f}s", flush=True)
        cache = work / f"{source['id']}-normalized.json"
        signature = dict(source_sha256=sha(path), filters=filters, samples=samples)
        if not (wav.exists() and cache.exists() and json.loads(cache.read_text()) == signature):
            run(['ffmpeg', '-y', '-hide_banner', '-nostats', '-i', str(path), '-vn',
                 '-af', filters, '-ar', str(rate), '-c:a', 'pcm_s24le', str(wav)],
                work / f"{source['id']}-normalization.log")
            cache.write_text(json.dumps(signature), encoding='utf-8')
        entries.append(dict(id=source['id'], path=path.as_posix(), sha256=sha(path),
                            duration=duration, frames=int(video['nb_frames']),
                            start=sum(e['duration'] for e in entries),
                            samples=samples, audio=wav.as_posix(),
                            original_probe=info))
    for name, key in [('sources', 'path'), ('audio', 'audio')]:
        (work / f'{name}.ffconcat').write_text(
            'ffconcat version 1.0\n' + ''.join(f"file '{e[key]}'\n" for e in entries),
            encoding='utf-8')
    soundtrack = work / 'soundtrack-normalized.wav'
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i',
         str(work / 'audio.ffconcat'), '-c:a', 'copy', str(soundtrack)])
    chapter_text = ';FFMETADATA1\n' + 'title=' + plan['title'] + '\n'
    for n, entry in enumerate(entries, 1):
        label = 'Заставка' if entry['id'] == 'intro' else f"Часть {n - 1}"
        chapter_text += (f"[CHAPTER]\nTIMEBASE=1/1000000\n"
                         f"START={round(entry['start'] * 1000000)}\n"
                         f"END={round((entry['start'] + entry['duration']) * 1000000)}\n"
                         f"title={label}\n")
    chapter_path = work / 'chapters.ffmetadata'
    chapter_path.write_text(chapter_text, encoding='utf-8')
    output = root / plan['output_filename']
    print('Muxing original video and normalized AAC audio', flush=True)
    run(['ffmpeg', '-y', '-hide_banner', '-nostats', '-f', 'concat', '-safe', '0',
         '-i', str(work / 'sources.ffconcat'), '-i', str(soundtrack),
         '-i', str(chapter_path), '-map', '0:v:0', '-map', '1:a:0',
         '-map_metadata', '2', '-map_chapters', '2', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', audio['aac_bitrate'], '-ar', str(rate),
         '-metadata:s:a:0', 'language=rus', '-metadata:s:v:0', 'language=und',
         '-movflags', '+faststart', str(output)], work / 'render.log')
    manifest = dict(title=plan['title'], sources=entries, audio=audio,
                    output=str(output), reference_audio=str(soundtrack),
                    duration=sum(e['duration'] for e in entries),
                    frames=sum(e['frames'] for e in entries))
    (work / 'timeline.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'YouTube-title.txt').write_text(plan['title'] + '\n', encoding='utf-8')
    shutil.copy2(args.source.with_name('YouTube-description-Russian.txt'), root)
    print(f'Finished: {output}', flush=True)


if __name__ == '__main__':
    main()
