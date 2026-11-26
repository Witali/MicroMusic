"""Prepare the pinned public PCM sources for the local excitation experiment.

Only standard-library Python and existing repository audio are used. Generated
PCM/WAV data stay below ignored build/local-noise/sources/.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import wave

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OUTPUT = REPO / 'build/local-noise/sources'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    retained = REPO / 'Codecs/LPX/research/lbg1-2026-11-26/results.json'
    prior = json.loads(retained.read_text())['inputs']
    helper_path = REPO / 'Codecs/LPX/research/lbg1-2026-11-26/prepare_sources.py'
    spec = importlib.util.spec_from_file_location('local_noise_resampler', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in prior['sources']:
        path = REPO / item['source']
        if sha(path) != item['source_sha256']:
            raise ValueError('Public source changed: ' + item['clip'])
        with wave.open(str(path), 'rb') as f:
            if f.getnchannels() != 1 or f.getsampwidth() != 2:
                raise ValueError('Expected mono PCM16')
            rate = f.getframerate()
            data = f.readframes(f.getnframes())
        if rate == 7500:
            samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
            samples = helper.resample16_15(samples)
            data = struct.pack('<' + 'h' * len(samples), *samples)
        elif rate != 8000:
            raise ValueError('Unexpected source sample rate')
        if hashlib.sha256(data).hexdigest() != item['pcm_sha256']:
            raise ValueError('Prepared PCM differs from the pinned corpus')
        pcm = OUTPUT / (item['clip'] + '.source.pcm')
        pcm.write_bytes(data)
        with wave.open(str(pcm.with_suffix('.wav')), 'wb') as f:
            f.setparams((1, 2, 8000, len(data) // 2, 'NONE', 'not compressed'))
            f.writeframes(data)
        rows.append(dict(item, pcm=pcm.relative_to(REPO).as_posix()))
    report = dict(schema='local-noise-public-sources-v1', sources=rows,
        method='Pinned complete public8k inputs; identical scalar Kaiser5 resampling, previously cross-checked against SciPy. No fitted gain/delay.',
        preparation_sha256=sha(Path(__file__)), resampler_sha256=sha(helper_path),
        pinned_reference_sha256=sha(retained))
    (OUTPUT / 'sources.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Verified four complete public PCM sources', flush=True)


if __name__ == '__main__':
    main()
