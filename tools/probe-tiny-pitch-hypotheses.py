"""Try generic source-derived F0 hypotheses without changing the Tiny decoder."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed
from tiny_period import pack_tiny
from tiny_pitch_hypotheses import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--baseline-model', type=Path, help='Optional protected incumbent associated with this complete source')
    p.add_argument('--baseline-words', type=int, choices=(4, 8), default=8)
    p.add_argument('--words', nargs='+', type=int, choices=(4, 8), default=[4, 8])
    p.add_argument('--seed', type=int, default=23230)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    original, sr = sf.read(a.reference, dtype='float64')
    baseline = json.loads(a.baseline_model.read_text(encoding='utf-8')) if a.baseline_model else None
    try:
        if sr != 7500:
            raise ValueError('Input must already be mono7500; this tool does not resample or normalize')
        reference, incumbent, selected, report = run(original, baseline_model=baseline,
            words=tuple(a.words), baseline_words=a.baseline_words, seed=a.seed)
    except ValueError as error:
        report = dict(schema='tiny-pitch-hypotheses-v1', status='unsupported-input', error=str(error),
                      reference_sha256=sha(a.reference.read_bytes()), sample_rate=sr,
                      input_gain_changed=False, input_dc_removed=False)
        (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
        print(json.dumps(report), flush=True)
        return 2
    report.update(status='baseline-unchanged' if report['baseline_fallback'] else 'improved-candidate',
                  reference_sha256=sha(a.reference.read_bytes()),
                  baseline_model_path=(a.baseline_model.relative_to(ROOT).as_posix() if a.baseline_model and a.baseline_model.is_relative_to(ROOT)
                                       else str(a.baseline_model) if a.baseline_model else None),
                  baseline_model_sha256=sha(a.baseline_model.read_bytes()) if a.baseline_model else None)
    if a.baseline_model:
        shutil.copyfile(a.baseline_model, a.output/'baseline-model.json')
    else:
        (a.output/'baseline-model.json').write_text(json.dumps(incumbent, indent=2)+'\n', encoding='utf-8', newline='\n')
    if report['baseline_fallback']:
        shutil.copyfile(a.output/'baseline-model.json', a.output/'model.json')
    else:
        (a.output/'model.json').write_text(json.dumps(selected, indent=2)+'\n', encoding='utf-8', newline='\n')
    packed = pack_tiny(selected)
    (a.output/'flash-data.bin').write_bytes(packed['flash_data'])
    (a.output/'eeprom.bin').write_bytes(packed['eeprom'])
    (a.output/'expected.raw').write_bytes(decode_fixed(selected).tobytes())
    report['selected_model_sha256'] = sha((a.output/'model.json').read_bytes())
    report['exact_baseline_model_file_retained'] = (report['baseline_fallback'] and
        (a.output/'model.json').read_bytes() == (a.output/'baseline-model.json').read_bytes())
    paths = (Path(__file__), CODEC/'tiny_pitch_hypotheses.py', CODEC/'new_tiny_encoder.py',
             CODEC/'period_wave.py', CODEC/'speech_pitch.py', CODEC/'speech_regression.py',
             CODEC/'spectrogram_objective.py', CODEC/'fixed_period.py', CODEC/'tiny_period.py',
             CODEC/'tiny/firmware.S')
    report['sources_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in paths}
    presentation = SpectralObjective(reference)
    signals = [reference, (decode_fixed(incumbent).astype(float)-128)/128,
               (decode_fixed(selected).astype(float)-128)/128]
    signals = [sosfilt(presentation.hp, value) for value in signals]
    signals = [value*presentation.rms/(np.sqrt(np.mean(value*value))+1e-20) for value in signals]
    gain = .85/max(float(np.max(abs(value))) for value in signals)
    for name, value in zip(('original', 'before', 'after'), signals):
        sf.write(a.output/(name+'-matched.wav'), value*gain, 7500, subtype='PCM_16')
    sf.write(a.output/'comparison.wav', np.concatenate([part for value in signals for part in (value*gain,np.zeros(2250))]),7500,subtype='PCM_16')
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({key:report[key] for key in ('status','baseline_label','selected_source','flash_data_budget','baseline','selected','elapsed_seconds')}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
