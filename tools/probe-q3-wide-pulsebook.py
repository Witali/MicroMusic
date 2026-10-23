"""Reproducible 48-case PC-only fractional-state Q3 diagnostic.

No joint refitting, AVR size, timing or hardware feasibility is claimed.
Every rejected combination remains in the report with its actual guard counts.
"""
import argparse
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np
from pystoi import stoi
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from q3_wide_pulsebook import render
from q3_pulsebook import render as byte_render,validate as byte_validate,legacy_tables
from q3_pulsebook_pole import render as pole_render,validate as pole_validate
from hq4_core import pack_stream
from spectrogram_objective import SpectrogramObjective

DEFAULT_MODELS = (
    'ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json',
    'ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json',
    'build/q3-pulsebook/vinni/best_spectrum/model.json',
    'build/q3-pulsebook/vinni/best_stoi/model.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scaled_frames(frames,scale):
    result = frames.copy()
    result[:,1] = (result[:,1] & 48)|np.minimum(15,np.rint((result[:,1] & 15)*scale)).astype(np.uint8)
    return result


def configurations():
    return [(bits,nearest,scale) for bits in (2,4) for nearest in (False,True) for scale in (.65,1.,1.35)]


def resolve_model(path):
    path = Path(path)
    if path.is_file():
        return path
    # The two temporary sources have byte-identical retained initial-study
    # counterparts. Record both requested and resolved locations explicitly.
    relative = path.as_posix()
    for name in ('best_spectrum','best_stoi'):
        if relative.endswith(f'build/q3-pulsebook/vinni/{name}/model.json'):
            retained = ROOT/f'ATtiny13A/Sound/research/q3-pulsebook/vinni/{name}/model.json'
            if retained.is_file():
                return retained
    raise FileNotFoundError('Missing local diagnostic model; no download is attempted')


def run(reference_path,models,output):
    reference_path = Path(reference_path)
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or not np.all(np.isfinite(reference)):
        raise ValueError('Expected unchanged finite mono7500Hz original')
    objective = SpectrogramObjective(reference)
    rows,inputs = [],[]
    relative = lambda path:Path(path).resolve().relative_to(ROOT).as_posix() if Path(path).resolve().is_relative_to(ROOT) else Path(path).name
    for requested in models:
        path = resolve_model(requested)
        model = json.loads(path.read_text(encoding='utf-8'))
        f,d,b = np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16),np.asarray(model.get('pulsebook',legacy_tables()),np.int8)
        pole = model['schema'] == 'hq4-q3-pulsebook-pole-v1'
        if model['schema'] not in ('hq4-q3-v1','hq4-q3-rounded-v1','hq4-q3-pulsebook-v1','hq4-q3-pulsebook-pole-v1'):
            raise ValueError('Unknown coefficient mapping in diagnostic source model')
        (pole_validate if pole else byte_validate)(f,d,b,len(reference))
        source_nearest = bool(model.get('nearest',model['schema'] == 'hq4-q3-rounded-v1'))
        original_pcm,original_counts = (pole_render if pole else byte_render)(f,d,b,int(model.get('tilt_shift',1)),source_nearest)
        original_audio = (original_pcm.astype(float)-128)/128
        baseline = dict(stoi=float(stoi(reference,original_audio,sr)),**objective.evaluate(original_audio),
            wrap_counts=original_counts.tolist(),raw_mean=float(original_audio.mean()))
        source_index = len(inputs)
        stream = pack_stream(f,d)
        inputs.append(dict(requested_source=relative(requested),resolved_source=relative(path),model_sha256=sha(path),
            model_schema=model['schema'],extended_pole=pole,source_nearest=source_nearest,
            tilt_shift=int(model.get('tilt_shift',1)),samples=len(reference),stream_sha256=hashlib.sha256(stream).hexdigest(),
            stream_base64=base64.b64encode(stream).decode('ascii'),pulsebook_int8_row_major=b.ravel().tolist(),
            table_sha256=hashlib.sha256(b.tobytes()).hexdigest(),byte_baseline=baseline))
        if int(model.get('tilt_shift',1)) != 1:
            raise ValueError('This diagnostic has fixed T1 de-emphasis; other profiles need a separately defined experiment')
        for bits,nearest,scale in configurations():
            trial = scaled_frames(f,scale)
            pcm,counts,maximum = render(trial,d,b,bits,nearest,pole)
            audio = (pcm.astype(float)-128)/128
            passed = not bool(np.any(counts))
            row = dict(source_index=source_index,fractional_bits=bits,nearest=nearest,gain_scale=scale,
                extended_pole=pole,status='complete' if passed else 'rejected',
                guard_counts=dict(zip(('product_signed16','lattice_signed16','tilt_signed16','pwm_signed8'),map(int,counts))),
                maximum_absolute=dict(zip(('product_scaled_units','lattice_scaled_units','tilt_scaled_units'),map(int,maximum))),
                pre_pwm_peak_bound=float(maximum[2]/(1 << bits)),
                observed_pcm_peak_signed=int(abs(pcm.astype(np.int16)-128).max()),raw_mean=float(audio.mean()),
                raw_rms=float(np.sqrt(np.mean(audio**2))),
                trial_stream_sha256=hashlib.sha256(pack_stream(trial,d)).hexdigest())
            if passed:
                row['metrics'] = dict(stoi=float(stoi(reference,audio,sr)),**objective.evaluate(audio))
                row['pcm_sha256'] = hashlib.sha256(pcm.tobytes()).hexdigest()
                row['target_met'] = bool(row['metrics']['stoi'] >= .9 and row['metrics']['spectrogram_loss'] <= .344975554)
            else:
                row['rejection'] = 'At least one signed16 internal/product or signed8 PWM guard exceeded; wrapped PCM is not scored as valid audio'
                row['metrics'],row['target_met'] = None,False
            rows.append(row)
    complete = [r for r in rows if r['status'] == 'complete']
    report = dict(schema='q3-wide-pulsebook-diagnostic-v1',reference_sha256=sha(reference_path),sample_rate=sr,
        samples=len(reference),input_policy='Full unchanged original, no gain/DC/crop/resampling changes',
        gain_policy='Frame gain=min(15,rint(old_gain*scale)); preserve old modebits48; NumPy nearest ties-to-even',
        internal_arithmetic='Wide integer state, audited against signed16 limits; no internal wrapping/clipping. Trials with any guard count reject.',
        output_arithmetic='Always nearest PWM rounding floor((T1state+2**(fractional_bits-1))/2**fractional_bits), independent of lattice nearest flag; modulo byte overflow rejects',
        source_mode_policy='Model pulsebook or exact legacy tables; extended_pole iff schema hq4-q3-pulsebook-pole-v1',
        guard_counter_policy='Counts evaluated for every configured combination, including rejected cases; no selective missing rows',
        avr_implemented=False,avr_code_bytes=None,avr_cycles=None,avr_sram_bytes=None,hardware_tested=False,
        target_met=any(r['target_met'] for r in rows),inputs=inputs,cases=rows,
        totals=dict(cases=len(rows),complete=len(complete),rejected=len(rows)-len(complete)),
        conclusion=('At least one fixed-parameter diagnostic meets the numerical target; no AVR feasibility or general-quality claim.' if any(r['target_met'] for r in rows) else
            'Fixed-parameter precision diagnostic only. Fractional states alone did not establish the hard quality target; no joint-refit or architecture impossibility claim.'),
        best_stoi_case=max(complete,key=lambda r:r['metrics']['stoi']) if complete else None,
        best_spectrum_case=min(complete,key=lambda r:r['metrics']['spectrogram_loss']) if complete else None,
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest()
            for p in (Path(__file__),CODEC/'q3_wide_pulsebook.py',CODEC/'q3_pulsebook.py',CODEC/'q3_pulsebook_pole.py',CODEC/'spectrogram_objective.py')},
        runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','numba','pystoi','soundfile')})
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(**report['totals'],target_met=report['target_met'],best_stoi=report['best_stoi_case']['metrics'],best_spectrum=report['best_spectrum_case']['metrics'])))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,default=ROOT/'web-player/audio/originals/vinni.wav')
    p.add_argument('--model',action='append',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'build/q3-wide-pulsebook-repro/report.json')
    a = p.parse_args()
    run(a.reference,a.model or [ROOT/path for path in DEFAULT_MODELS],a.output)


if __name__ == '__main__':
    main()
