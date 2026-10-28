"""Execute exactly the frozen 16-case quiet-amplitude diagnostic, once."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[5]
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
PROTOCOL = Path(__file__).resolve().parents[1] / 'PROTOCOL.md'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n',
                    encoding='utf-8', newline='\n')


def sources():
    paths = [Path(__file__), PROTOCOL, *(ACTIVE / 'tools').glob('*.py'),
             *(p for p in (ACTIVE / 'src').glob('*') if p.is_file())]
    return {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p.read_bytes()) for p in paths}


def main(args):
    out = args.output.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()) or out.exists():
        raise ValueError('A fresh owned output directory under ignored build/ is required')
    out.mkdir(parents=True)
    (out / 'tmp').mkdir()
    tempfile.tempdir = str(out / 'tmp')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ['NUMBA_CACHE_DIR'] = str(out / 'numba-cache')
    sys.path.insert(0, str(ACTIVE / 'tools'))
    import numpy as np
    import soundfile as sf
    from batch_decoder import BatchSession
    from q0_model import table
    import speech_compact as compact
    import speech_v4 as v4
    from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
    from voice_character import compare_voice, track_pitch

    frozen = sources()
    runtime = {'python': sys.version, 'platform': platform.platform(),
               'packages': {name: importlib.metadata.version(name)
                            for name in ('numpy', 'numba', 'scipy', 'soundfile')}}
    public = {'schema': 'lpx-quiet-amplitude-synthetic-v1', 'status': 'running',
              'protocol_commit': '73e7dd1a', 'source_sha256': frozen, 'runtime': runtime,
              'samples_per_case': 8000, 'rate': 8000, 'cases_expected': 16, 'rows': []}
    private = {'schema': 'lpx-quiet-amplitude-synthetic-private-v1', 'rows': []}

    def descriptor(pcm):
        a = pcm.astype(np.float64)
        return {'samples': len(a), 'peak_pcm16': int(np.max(abs(a))),
                'rms_pcm16': float(np.sqrt(np.mean(a*a))), 'mean_pcm16': float(np.mean(a)),
                'integer_levels': len(np.unique(pcm)), 'nonzero_samples': int(np.count_nonzero(pcm))}

    def histogram(values):
        return {str(k): v for k, v in sorted(Counter(map(int, values)).items())}

    t = np.arange(8000, dtype=np.float64)
    analytic = (.7 * np.sin(2*np.pi*200*t/8000) + .2 * np.sin(2*np.pi*400*t/8000)
                + .1 * np.sin(2*np.pi*600*t/8000))
    begin = time.perf_counter()
    with BatchSession('batch', v3_features=124, speech=True, speech_compact=True) as common, \
         BatchSession('batch', v3_features=124, speech=True, speech_compact=True, compact_only=True) as only:
        private['native_library_sha256'] = {
            'common': sha(common.library_path.read_bytes()), 'v5_only': sha(only.library_path.read_bytes())}
        for scale in (1, 4, 32, 1024):
            for profile in (4, 6):
                for pre in (0, 13926):
                    assert sources() == frozen, 'Source changed during the frozen run'
                    case = 'scale-%04d-p%d-pre-%05d' % (scale, profile, pre)
                    reference = np.rint(scale * analytic).astype(np.int16)
                    folder = out / case
                    folder.mkdir()
                    sf.write(folder / 'reference.wav', reference, 8000, subtype='PCM_16')
                    source_track = track_pitch(reference)
                    row = {'case': case, 'nominal_scale': scale, 'profile': profile,
                           'preQ14': pre, 'source': descriptor(reference),
                           'source_period_windows': int(source_track.voiced.sum()),
                           'source_period_status': 'observed' if source_track.voiced.any() else 'unassessed',
                           'status': 'running'}
                    private_row = {'case': case, 'reference_pcm16_sha256': sha(reference.astype('<i2').tobytes())}
                    started = time.perf_counter()
                    try:
                        old, expected, encoder = v4.encode(reference, profile, common, pre=pre, bandwidth=.97)
                        blob, packed = compact.repack(old)
                        assert len(expected) == len(reference) == 8000
                        np.testing.assert_array_equal(v4.decode_model(old), expected)
                        np.testing.assert_array_equal(compact.decode_model(blob), expected)
                        duties = pwm_duties(expected)
                        comparisons = 0
                        for decoder, stream in ((common, old), (common, blob), (only, blob)):
                            np.testing.assert_array_equal(decoder.decode_one_s16(stream, 8000), expected)
                            np.testing.assert_array_equal(decoder.decode_one(stream, 8000), duties)
                            comparisons += 2
                        pwm = pwm_pcm16(expected)
                        source_pwm = pwm_pcm16(reference)
                        values = compact.unpack(blob)
                        params, pulses = values[3:5]
                        steps = table('scale_table.inc')
                        actual_steps = [int(steps[p[0] * 8]) for p in params]
                        row.update(
                            status='complete', v4_bytes=len(old), v5_bytes=len(blob),
                            v5_payload_bits=packed['payload_bits'],
                            v4_v5_all_pcm_exact=True, native_output_domain_comparisons=comparisons,
                            native_model_pcm_pwm_exact=True, native_pcm16=descriptor(expected),
                            fixed_pwm_pcm16=descriptor(pwm),
                            non_neutral_pwm_samples=int(np.count_nonzero(duties != 128)),
                            reference_fixed_pwm_non_neutral_samples=int(np.count_nonzero(source_pwm)),
                            pcm16_waveform=error_metrics(reference, expected, False),
                            pwm8_waveform=error_metrics(reference, pwm, False),
                            pcm16_voice=compare_voice(reference, expected, reference_track=source_track),
                            pwm8_voice=compare_voice(reference, pwm, reference_track=source_track),
                            stored_parameters={'tuples': len(params), 'scale_code_histogram': histogram(p[0] for p in params),
                                               'scale_step_q14_histogram': histogram(actual_steps),
                                               'gain_histogram': histogram(p[2] for p in params),
                                               'lag_histogram': histogram(p[1] for p in params),
                                               'innovation_amplitude_histogram': histogram(p[1] for p in pulses),
                                               'zero_step_tuples': sum(v == 0 for v in actual_steps)},
                            seconds=time.perf_counter() - started)
                        (folder / 'v4.l4hy').write_bytes(old)
                        (folder / 'v5.l4hy').write_bytes(blob)
                        sf.write(folder / 'decoded-pcm16.wav', expected, 8000, subtype='PCM_16')
                        sf.write(folder / 'decoded-pwm.wav', pwm.astype(np.int16), 8000, subtype='PCM_16')
                        private_row.update(v4_stream_sha256=sha(old), v5_stream_sha256=sha(blob),
                                           decoded_pcm16_sha256=sha(expected.astype('<i2').tobytes()),
                                           decoded_pwm_sha256=sha(duties.tobytes()), encoder=encoder)
                    except Exception as error:
                        row.update(status='failed', error_type=type(error).__name__, seconds=time.perf_counter() - started)
                        private_row.update(error_text=str(error))
                    public['rows'].append(row)
                    private['rows'].append(private_row)
                    save(out / 'summary.json', public)
                    save(out / 'results-private.json', private)
                    print(json.dumps({k: row[k] for k in ('case', 'status', 'source_period_windows')}), flush=True)
    assert sources() == frozen, 'Source changed before finalizing the frozen run'
    assert len(public['rows']) == 16
    public.update(status='complete' if all(r['status'] == 'complete' for r in public['rows']) else 'complete_with_failures',
                  actual_cases=16, seconds=time.perf_counter() - begin,
                  scope='Sixteen analytic synthetic cases; no fit tuning, corpus, firmware, true-F0 or perceptual-quality claim.')
    save(out / 'summary.json', public)
    save(out / 'results-private.json', private)
    print(json.dumps({'status': public['status'], 'cases': 16, 'seconds': public['seconds']}), flush=True)
    return int(public['status'] != 'complete')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    raise SystemExit(main(parser.parse_args()))
