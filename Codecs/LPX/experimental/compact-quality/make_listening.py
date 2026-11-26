"""Wrap verified public P3 comparison PCM in WAV; never fit gain or delay."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import wave

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
MATRIX = HERE / 'results-ensemble-matrix.json'
MATRIX_SHA = '349ca6c74828d7e23b5eb3036dfc5e109f76523b6757b07d3fcf4abceea67a24'


def checked(relative, expected):
    path = (REPO / relative).resolve()
    path.relative_to(REPO.resolve())
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('Frozen public comparison artifact changed')
    return payload


def wav(path, payload, rate, samples):
    if len(payload) != samples * 2:
        raise ValueError('Expected complete mono PCM16 payload')
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(payload)
    with wave.open(str(path), 'rb') as output:
        if (output.getnframes() != samples or output.getframerate() != rate
                or output.readframes(samples + 1) != payload):
            raise AssertionError('WAV wrapping changed PCM payload or geometry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO / 'build/compact-quality/listening-ensemble')
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to((REPO / 'build').resolve())
    if output == (REPO / 'build').resolve():
        raise ValueError('Use a dedicated ignored listening directory')
    data = checked(MATRIX.relative_to(REPO), MATRIX_SHA)
    matrix = json.loads(data)
    if not matrix['complete'] or len(matrix['cases']) != 8:
        raise ValueError('Expected the complete frozen public eight-case matrix')
    output.mkdir(parents=True, exist_ok=True)
    report = dict(matrix_sha256=MATRIX_SHA, cases=[], fitted_gain=False,
                  fitted_delay=False, resampled=False,
                  scope='Rejected raw candidates for listening, not protected improvements. PWM WAV is the fixed duty-average model, not a physical board recording.')
    for case in matrix['cases']:
        if not case['protection']['raw_changed']:
            continue
        rate, samples = case['baseline']['rate'], case['baseline']['samples']
        source = checked(case['source'], case['source_sha256'])
        row = dict(name=case['name'], target=case['target'], samples=samples, rate=rate,
                   baseline_bytes=case['baseline']['bytes'], raw_bytes=case['raw-ensemble']['bytes'],
                   rejection_bits=case['protection']['rejection_bits'], files={})
        streams = {'reference': source}
        for label in ('baseline', 'raw-ensemble', 'protected'):
            artifact = case['artifacts'][label]['pcm']
            streams[label] = checked(artifact['path'], artifact['sha256'])
        if streams['baseline'] != streams['protected']:
            raise AssertionError('Protected file must remain the exact baseline here')
        for label in ('reference', 'baseline', 'raw-ensemble'):
            payload = streams[label]
            if case['target'] == 'pwm' and label != 'reference':
                values = (max(0, min(255, 128 + ((((value + 1) // 2) * 130 + 8192) >> 14)))
                          for value, in struct.iter_unpack('<h', payload))
                payload = b''.join(struct.pack('<h', (duty - 128) * 256) for duty in values)
            name = case['name'] + '-' + label + '.wav'
            wav(output / name, payload, rate, samples)
            row['files'][label] = dict(file=name, sha256=hashlib.sha256((output / name).read_bytes()).hexdigest())
        report['cases'].append(row)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Verified', len(report['cases']) * 3, 'level-preserved public WAVs')


if __name__ == '__main__':
    main()
