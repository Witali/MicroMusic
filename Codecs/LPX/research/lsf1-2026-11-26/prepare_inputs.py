"""Prepare the identical public corpus and current LPX baselines for LSF1.

An optional local cache is accepted only when every source/model/LPX/PCM hash
matches the retained LG1 comparison. Otherwise regenerate with the same current
host encoder. No media is committed or downloaded.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import wave

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PREVIOUS = HERE.parent / 'lbg1-2026-11-26'
OUTPUT = REPO / 'build/lsf1-common'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse', type=Path, help='Previous ignored build/lbg1-common directory')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    old = json.loads((PREVIOUS / 'results.json').read_text())
    sources = []
    scalar = load('lsf1_source_preparation', PREVIOUS / 'prepare_sources.py')
    for source in old['inputs']['sources']:
        original = REPO / source['source']
        if sha(original) != source['source_sha256']:
            raise ValueError('Public source differs from the pinned comparison')
        target = OUTPUT / (source['clip'] + '.source.pcm')
        if args.reuse:
            cached = args.reuse / target.name
            if sha(cached) != source['pcm_sha256']:
                raise ValueError('Cached source PCM differs')
            shutil.copyfile(cached, target)
        else:
            import struct
            with wave.open(str(original), 'rb') as f:
                if f.getnchannels() != 1 or f.getsampwidth() != 2:
                    raise ValueError('Expected mono PCM16 WAV')
                raw = f.readframes(f.getnframes())
                rate = f.getframerate()
            samples = list(struct.unpack('<' + 'h' * (len(raw) // 2), raw))
            if rate == 7500:
                samples = scalar.resample16_15(samples)
            elif rate != 8000:
                raise ValueError('Unexpected source rate')
            target.write_bytes(struct.pack('<' + 'h' * len(samples), *samples))
        if sha(target) != source['pcm_sha256']:
            raise ValueError('Prepared source PCM differs')
        with wave.open(str(target.with_suffix('.wav')), 'wb') as f:
            f.setparams((1, 2, 8000, source['samples'], 'NONE', 'not compressed'))
            f.writeframes(target.read_bytes())
        sources.append(source)
    save(OUTPUT / 'sources.json', dict(method=old['inputs']['method'], sources=sources,
         note='PCM hashes verified against the prior scalar/SciPy cross-checked corpus.'))
    builder = load('lsf1_probe_builder', PREVIOUS / 'build_probe.py')
    builder.OUTPUT = OUTPUT
    builder.main()
    baseline = load('lsf1_baseline_encoder', PREVIOUS / 'prepare_baselines.py')
    baseline.BUILD = OUTPUT
    (OUTPUT / 'baselines').mkdir(exist_ok=True)
    if args.reuse:
        cache_manifest = args.reuse / 'baselines.json'
        cache_metadata = json.loads(cache_manifest.read_text())
        rows = []
        for case in old['cases']:
            clip, level = case['name'].rsplit('-p', 1)
            item = case['baseline']
            expected = dict(lpx=item['sha256'], pcm=item['pcm_sha256'], model=item['model_sha256'])
            row = dict(clip=clip, level=int(level), calls=4)
            for extension, digest in expected.items():
                name = case['name'] + '.' + extension
                source = args.reuse / 'baselines' / name
                if sha(source) != digest:
                    raise ValueError('Cached baseline differs: ' + name)
                destination = OUTPUT / 'baselines' / name
                shutil.copyfile(source, destination)
                row[extension] = destination.relative_to(REPO).as_posix()
            row['reference'] = (OUTPUT / (clip + '.source.pcm')).relative_to(REPO).as_posix()
            row['reference_sha256'] = case['reference_sha256']
            row['sha256'] = expected
            # The cache's metadata/metrics are not authenticated by matching
            # audio bytes. Validate with this build and recompute diagnostics.
            native = OUTPUT / 'baselines' / (case['name'] + '.validation.pcm')
            subprocess.run([str(OUTPUT / 'probe'), 'decode', str(REPO / row['lpx']), str(native)], check=True)
            if sha(native) != expected['pcm']:
                raise ValueError('Current native decode differs: ' + case['name'])
            row['metrics'] = json.loads(subprocess.check_output([
                str(OUTPUT / 'probe'), 'measure', str(REPO / row['reference']), str(native)], text=True))
            save(OUTPUT / 'baselines' / (case['name'] + '.json'), row)
            rows.append(row)
        save(OUTPUT / 'baselines.json', dict(schema='lsf1-current-lpx-baselines-v1',
             baseline_revision=old['baseline_revision'], current_head=baseline.head(),
             method='Byte-identical pinned current calls4 baselines; same public complete PCM inputs.',
             cache_manifest_sha256=sha(cache_manifest),
             recorded_cache_encoding_probe_sha256=cache_metadata.get('probe_sha256'),
             validation_probe_sha256=sha(OUTPUT / 'probe'),
             encoding_provenance='Pinned LPX/model/PCM byte hashes from prior comparison; cached metrics are not reused.',
             sources=json.loads((OUTPUT / 'sources.json').read_text()), rows=rows))
    else:
        baseline.main()
        for case in old['cases']:
            item = case['baseline']
            for ext, digest in [('lpx', item['sha256']), ('pcm', item['pcm_sha256']), ('model', item['model_sha256'])]:
                if sha(OUTPUT / 'baselines' / (case['name'] + '.' + ext)) != digest:
                    raise ValueError('Fresh current baseline changed: ' + case['name'])
    print('Verified all four source PCM files and eight LPX/model/PCM baselines', flush=True)


if __name__ == '__main__':
    main()
