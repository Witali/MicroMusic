"""Fresh readback validation of the completed frozen 16-case experiment."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'),
               str(Path(__file__).resolve().parent)]

import numpy as np
import soundfile as sf
from batch_decoder import BatchDecoder
import speech_compact as compact
import speech_v4 as v4
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16
from voice_character import compare_voice, track_pitch
from run_synthetic import sources


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(folder):
    folder = folder.resolve()
    if not folder.is_relative_to((ROOT / 'build').resolve()):
        raise ValueError('The experiment must remain under ignored build/')
    summary = json.loads((folder / 'summary.json').read_text())
    private = json.loads((folder / 'results-private.json').read_text())
    assert summary['status'] == 'complete' and summary['source_sha256'] == sources()
    assert len(summary['rows']) == len(private['rows']) == 16
    libraries = {sha(p.read_bytes()): p for p in (folder / 'tmp').rglob('*.so')}
    common, only = [BatchDecoder(libraries[private['native_library_sha256'][key]])
                    for key in ('common', 'v5_only')]
    observed = []
    comparisons = 0
    n = np.arange(8000, dtype=np.float64)
    analytic = .7*np.sin(2*np.pi*200*n/8000) + .2*np.sin(2*np.pi*400*n/8000) + .1*np.sin(2*np.pi*600*n/8000)
    for row, pinned in zip(summary['rows'], private['rows']):
        assert row['case'] == pinned['case'] and row['status'] == 'complete'
        scale, profile, pre = row['nominal_scale'], row['profile'], row['preQ14']
        observed.append((scale, profile, pre))
        case = folder / row['case']
        reference, rate = sf.read(case / 'reference.wav', dtype='int16')
        assert rate == 8000 and len(reference) == 8000
        np.testing.assert_array_equal(reference, np.rint(scale*analytic).astype(np.int16))
        assert sha(reference.astype('<i2').tobytes()) == pinned['reference_pcm16_sha256']
        old, new = (case / 'v4.l4hy').read_bytes(), (case / 'v5.l4hy').read_bytes()
        assert sha(old) == pinned['v4_stream_sha256'] and sha(new) == pinned['v5_stream_sha256']
        assert len(old) == row['v4_bytes'] and len(new) == row['v5_bytes']
        assert v4.unpack(old)[1] == compact.unpack(new)[5] == pre
        assert old[5] == profile == new[5]
        assert compact.repack(old)[0] == new
        pcm = compact.decode_model(new)
        np.testing.assert_array_equal(v4.decode_model(old), pcm)
        duties = pwm_duties(pcm)
        assert sha(pcm.astype('<i2').tobytes()) == pinned['decoded_pcm16_sha256']
        assert sha(duties.tobytes()) == pinned['decoded_pwm_sha256']
        for decoder, stream in ((common, old), (common, new), (only, new)):
            np.testing.assert_array_equal(decoder.decode_one_s16(stream, 8000), pcm)
            np.testing.assert_array_equal(decoder.decode_one(stream, 8000), duties)
            comparisons += 2
        pwm = pwm_pcm16(pcm)
        for file, expected in (('decoded-pcm16.wav', pcm), ('decoded-pwm.wav', pwm)):
            actual, rate = sf.read(case / file, dtype='int16')
            assert rate == 8000
            np.testing.assert_array_equal(actual, expected)
        track = track_pitch(reference)
        assert compare_voice(reference, pcm, reference_track=track) == row['pcm16_voice']
        assert compare_voice(reference, pwm, reference_track=track) == row['pwm8_voice']
        assert error_metrics(reference, pcm, False) == row['pcm16_waveform']
        assert error_metrics(reference, pwm, False) == row['pwm8_waveform']
        assert int(np.count_nonzero(duties != 128)) == row['non_neutral_pwm_samples']
        assert int(np.count_nonzero(pwm_pcm16(reference))) == row['reference_fixed_pwm_non_neutral_samples']
        histogram = {str(k): v for k, v in sorted(Counter(p[1] for p in compact.unpack(new)[4]).items())}
        assert histogram == row['stored_parameters']['innovation_amplitude_histogram']
    assert observed == [(s, p, e) for s in (1, 4, 32, 1024) for p in (4, 6) for e in (0, 13926)]
    assert summary['source_sha256'] == sources()
    receipt = {'schema': 'lpx-quiet-amplitude-synthetic-audit-v1', 'status': 'complete',
               'auditor_source_sha256': sha(Path(__file__).read_bytes()), 'cases': 16,
               'full_samples_per_case': 8000, 'fresh_native_domain_checks': comparisons,
               'all_reference_formula_wav_stream_model_native_pcm_pwm_metrics_exact': True,
               'no_fit_cases': 0, 'dropped_cases': 0,
               'scope': 'Fresh readback of the same16 cases; not additional independent signals or new fitting.'}
    (folder / 'audit.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    main(parser.parse_args().folder)
