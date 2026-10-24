"""Verify the actual deliverable against its complete original recordings.

Adapted to Russian, variable-frame-rate phone footage from the verification
workflow in the personal narrated-project-video skill. No synthetic narration
or subtitles were requested. Decoded frame hashes prove every original frame
was retained. Loudness measurements are on the final AAC deliverable.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np


def run(command):
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result


def packets(path, stream, hashes=False):
    command = ['ffprobe', '-v', 'error', '-select_streams', stream,
               '-show_packets', '-show_entries', 'packet=dts_time,data_hash',
               '-of', 'json']
    if hashes:
        command += ['-show_data_hash', 'sha256']
    return json.loads(run(command + [str(path)]).stdout)['packets']


def frame_hashes(path, cache_dir):
    with Path(path).open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    cached = cache_dir / (checksum + '.json')
    if cached.exists():
        return json.loads(cached.read_text(encoding='utf-8'))
    result = run(['ffmpeg', '-v', 'error', '-reinit_filter', '0', '-i', str(path),
                  '-map', '0:v:0', '-an', '-fps_mode', 'passthrough',
                  '-f', 'framemd5', '-'])
    assert not result.stderr.strip(), result.stderr.decode('utf-8', errors='replace')
    hashes = [line.split(',')[-1].strip() for line in result.stdout.decode().splitlines()
              if line and not line.startswith('#')]
    cached.write_text(json.dumps(hashes) + '\n', encoding='utf-8')
    return hashes


def loudness(path, start=None, duration=None):
    command = ['ffmpeg', '-hide_banner', '-nostats']
    if start is not None:
        command += ['-ss', str(start)]
    if duration is not None:
        command += ['-t', str(duration)]
    command += ['-i', str(path)]
    command += ['-vn', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=50:print_format=json',
                '-f', 'null', '-']
    log = run(command).stderr.decode('utf-8', errors='replace')
    return json.loads(re.search(r'\{\s*"input_i".*?\}', log, re.S).group())


def decoded_audio(path):
    result = run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                  '-vn', '-ar', '24000', '-ac', '1', '-c:a', 'pcm_f32le',
                  '-f', 'f32le', '-'])
    return np.frombuffer(result.stdout, dtype='<f4')


def verify(path, timeline_path, reference, report_path):
    plan = json.loads(timeline_path.read_text(encoding='utf-8'))
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_format',
                          '-show_streams', '-show_chapters', '-of', 'json',
                          str(path)]).stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    sound = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height']) == (1920, 1080)
    assert int(video['nb_frames']) == plan['frames']
    assert abs(float(info['format']['duration']) - plan['duration']) < 0.12
    assert abs(float(sound['duration']) - plan['duration']) < 0.025
    assert sound['tags']['language'] == 'rus'
    assert len(info['chapters']) == len(plan['sources'])
    for chapter, source in zip(info['chapters'], plan['sources']):
        assert abs(float(chapter['start_time']) - source['start']) < 0.003
    # MP4 concat can insert SPS/PPS into packets without changing the picture.
    # Compare decoded frames instead of container-dependent packet bytes.
    cache_dir = timeline_path.parent / 'decoded-frame-hashes'
    cache_dir.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(frame_hashes, s['path'], cache_dir) for s in plan['sources']]
        final_job = pool.submit(frame_hashes, path, cache_dir)
        source_frames = [h for job in jobs for h in job.result()]
        final_frames = final_job.result()
    assert final_frames == source_frames, 'Decoded video content changed or missing'
    final_packets = packets(path, 'v:0')
    clocks = {}
    for stream, rows in [('v:0', final_packets), ('a:0', packets(path, 'a:0'))]:
        steps = np.diff([float(p['dts_time']) for p in rows])
        assert np.all(steps > 0), f'Nonmonotonic timestamps: {stream}'
        assert max(steps) < (0.14 if stream == 'v:0' else 0.025)
        clocks[stream] = dict(packets=len(rows), max_gap_seconds=float(max(steps)))
    print('All original decoded frames, duration, metadata and timestamps passed', flush=True)
    # frame_hashes already decoded every video frame with no errors. Decoding
    # audio below completes the decode check. A second null video mux would
    # quantize this phone's variable timestamps to 1/30 and produce artificial
    # duplicate-DTS errors despite the strictly increasing real packet times.
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(loudness, path)] + [
            pool.submit(loudness, path, s['start'], s['duration']) for s in plan['sources']]
        levels = [j.result() for j in jobs]
    (timeline_path.parent / 'loudness-measurements.json').write_text(
        json.dumps(levels, indent=2) + '\n', encoding='utf-8')
    for measurement, source in zip(levels[1:], plan['sources']):
        if source['id'] == 'intro':
            assert float(measurement['input_i']) < -60
            continue
        assert abs(float(measurement['input_i']) + 16) < 0.8, measurement
        assert float(measurement['input_tp']) <= -1.0, measurement
    actual, original = decoded_audio(path), decoded_audio(reference)
    assert abs(len(actual) - len(original)) <= 1024
    comparison = []
    for source in plan['sources']:
        start = round(source['start'] * 24000)
        end = min(len(actual), len(original), round((source['start'] + source['duration']) * 24000))
        if source['id'] == 'intro':
            assert float(np.sqrt(np.mean(actual[start:end] ** 2))) < 0.002
            corr = None
        else:
            corr = float(np.corrcoef(actual[start:end], original[start:end])[0, 1])
            assert corr > 0.99, (source['id'], corr)
        comparison.append(dict(id=source['id'], correlation=corr))
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = dict(file=str(path.resolve()), sha256=checksum, bytes=path.stat().st_size,
                  duration_seconds=float(info['format']['duration']),
                  resolution=[video['width'], video['height']],
                  frames=int(video['nb_frames']), video_frames='all original decoded frame hashes match',
                  decode_check='passed', packets=clocks,
                  final_aac_loudness=dict(overall=levels[0], parts=levels[1:]),
                  reference_audio=comparison)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--reference-audio', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    verify(args.video, args.timeline, args.reference_audio, args.report)
