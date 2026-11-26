"""Export fixed local reserve/Russian comparisons; no gain or delay fitting.

Generated audio and all source/artifact bindings remain in ignored build/.
The default is the first VCTK reserve ordinal, not a maximum-gain selection.
"""
import hashlib
import importlib.util
import json
import argparse
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
MATRIX_SHA = 'b5a5a92df4bf0c782c40c669ef499a74488867d15eca9bb11a000331755a5c98'
SPEC = importlib.util.spec_from_file_location('verified_wav_wrapper', HERE.parent / 'make_listening.py')
WRAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WRAP)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('reserve-00-pcm', 'vinni-pwm'), default='reserve-00-pcm')
    args = parser.parse_args()
    matrix = HERE / 'results-matrix.json'
    if hashlib.sha256(matrix.read_bytes()).hexdigest() != MATRIX_SHA:
        raise ValueError('Expected the complete frozen round2 matrix')
    public = json.loads(matrix.read_bytes())
    private = json.loads((REPO / 'build/compact-quality/round2/journal-matrix-private.json').read_bytes())
    if not public['complete'] or not private['complete'] or public['builds'] != private['builds']:
        raise ValueError('Expected matching immutable public/private records')
    name = args.case
    row = next(r for r in private['cases'] if r['name'] == name)
    if not row['selected_changed'] or row['rate'] != 8000:
        raise ValueError('Expected a selected 8k case')
    folder = 'listening-reserve-00' if name == 'reserve-00-pcm' else 'listening-russian-vinni'
    output = REPO / 'build/compact-quality/round2' / folder
    output.mkdir(parents=True, exist_ok=True)
    streams = {'reference': WRAP.checked(row['source'], row['source_sha256'])}
    sizes = {}
    for label, variant in (('current', 'baseline'), ('new', 'selected_output')):
        artifacts = row['artifacts'][variant]
        streams[label] = WRAP.checked(artifacts['pcm']['path'], artifacts['pcm']['sha256'])
        sizes[label] = len(WRAP.checked(artifacts['lpx']['path'], artifacts['lpx']['sha256']))
    if sizes['new'] > sizes['current']:
        raise ValueError('The actual baseline byte ceiling was exceeded')
    for label, payload in streams.items():
        if row['target'] == 'pwm' and label != 'reference':
            duties = (max(0, min(255, 128 + ((((value + 1) // 2) * 130 + 8192) >> 14)))
                      for value, in struct.iter_unpack('<h', payload))
            payload = b''.join(struct.pack('<h', (duty - 128) * 256) for duty in duties)
        WRAP.wav(output / (label + '.wav'), payload, 8000, row['samples'])
    manifest = dict(case=name, dataset='VCTK' if row['group'] == 'reserve' else 'Public project development clip',
                    samples=row['samples'], rate=8000, bytes=sizes,
                    fitted_gain=False, fitted_delay=False, resampled_after_decode=False,
                    output_model='Native PCM' if row['target'] == 'pcm' else 'Fixed PWM duty-average model',
                    public_matrix_sha256=MATRIX_SHA,
                    scope='Local posthoc listening of a fixed reserve/development case. No search or selection change; generated files remain ignored.')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Verified three local level-preserved mono8k PCM16 WAVs')


if __name__ == '__main__':
    main()
