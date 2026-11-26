"""Export level-preserved listening pairs from verified experiment artifacts.

PCM-target examples contain the decoded PCM. PWM-target examples apply the same
static PWM transfer as the quality evaluator; they are not hardware recordings
or simulated carrier/analog-filter output. Nothing is uploaded or committed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import wave

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wav(path, data, rate):
    with wave.open(str(path), 'wb') as f:
        f.setparams((1, 2, rate, len(data) // 2, 'NONE', 'not compressed'))
        f.writeframes(data)


def transfer(data):
    samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
    fixed = [(max(0, min(255, 128 + ((((s + 1) >> 1) * 130 + 8192) >> 14))) - 128) * 256
             for s in samples]
    return struct.pack('<' + 'h' * len(fixed), *fixed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=HERE / 'results-matrix.json')
    parser.add_argument('--case', action='append', dest='cases')
    args = parser.parse_args()
    report = json.loads(args.results.read_text())
    if not report.get('complete'):
        raise ValueError('Comparison is incomplete')
    names = {case['name'] for case in report['cases']}
    if args.cases and set(args.cases) - names:
        raise ValueError('Unknown listening case')
    output = REPO / 'build/local-noise/listening'
    output.mkdir(parents=True, exist_ok=True)
    receipt = []
    for case in report['cases']:
        if args.cases and case['name'] not in args.cases:
            continue
        directory = output / case['name']
        directory.mkdir(exist_ok=True)
        source = REPO / case['source']
        if sha(source) != case['source_sha256']:
            raise ValueError('Source changed')
        wav(directory / 'source.wav', source.read_bytes(), case['sample_rate'])
        for variant in ('baseline', 'final-noise', 'final-sse', 'raw-noise'):
            item = case['artifacts'][variant]
            pcm = REPO / item['pcm']
            if sha(pcm) != item['pcm_sha256']:
                raise ValueError('Decoded artifact changed')
            data = pcm.read_bytes()
            if case['quality_target'] == 'pwm':
                data = transfer(data)
            path = directory / (variant + '.wav')
            wav(path, data, case['sample_rate'])
            receipt.append(dict(case=case['name'], variant=variant,
                path=path.relative_to(REPO).as_posix(), sha256=sha(path),
                raw_unadmitted=variant == 'raw-noise', target=case['quality_target']))
    (output / 'manifest.json').write_text(json.dumps(dict(
        results_sha256=sha(args.results), no_fitted_gain_or_delay=True,
        pwm_scope='Static integer PWM transfer, no carrier/filter or hardware capture.',
        examples=receipt), indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Exported listening examples for', len(receipt) // 4, 'cases')


if __name__ == '__main__':
    main()
