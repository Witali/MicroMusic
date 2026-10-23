#!/usr/bin/env python3
"""Project trained period/noise waves into the unchanged exact tiny decoder.

The teacher supplies its co-trained pitch trajectory and waveform book. The
reference selects output gains/noise and scores complete decoded PCM. Code
bytes are deliberately excluded unless separately assembled by the builder.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed
from new_tiny_encoder import initialize_model
from period_wave import GAIN_LEVELS
from tiny_period import pack_tiny, unpack_tiny
from refine_period_helpers import atomic_json, matched_audio, digest


def teacher_analysis(teacher):
    base = teacher['base']
    frames = np.asarray(base['frames'],dtype=int)
    book = np.asarray(base['codebook'],dtype=float)/7
    gains = GAIN_LEVELS[frames[:,2]]*base['scale_u16']/65535*frames[:,3]
    shapes = book[frames[:,1]]*gains[:,None]
    return dict(shapes=shapes, f0=frames[:,0]*7500*32/65536*frames[:,3])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proposals',type=int,default=1000)
    a = p.parse_args()
    if a.proposals < 0:
        p.error('Proposal count must be nonnegative')
    reference,sr = sf.read(a.reference,dtype='float64')
    teacher = json.loads(a.model.read_text(encoding='utf-8'))
    if sr != 7500 or reference.ndim != 1 or len(reference) != teacher['base']['samples']:
        p.error('Reference/model shape mismatch')
    spec = importlib.util.spec_from_file_location('teacher_tiny_search',ROOT/'tools/train-tiny-speech.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    objective = SpectralObjective(reference,sr)
    analysis = teacher_analysis(teacher)
    a.output.mkdir(parents=True,exist_ok=True)
    report = dict(schema='period-teacher-tiny-projection-v1',reference_sha256=digest(a.reference.read_bytes()),
                  teacher_model_sha256=digest(a.model.read_bytes()),proposals=a.proposals,
                  avr_assembled=False, hardware_verified=False, code_size_measured=False,
                  decoder_code_excluded_from_size=True,candidates=[])
    best = None
    for words in (4,8):
        model = initialize_model(reference,teacher['base'],analysis,words,starts=8,seed=23171)
        search = module.TinySearch(model,objective,words=words,stoi_floor=0.,
                    spectral_ceiling=3.,max_peak=.99,max_data_bytes=65535,dc_choices=(7,),
                    voiced_only=True,residual_colors=(0,),allow_gain6=False,seed=23171)
        score = search.score(model)
        payload = pack_tiny(model)
        record = dict(words=words,**score,tiny_flash_data_bytes=len(payload['flash_data']),
                      eeprom_used_bytes=payload['constants']['EEPROM_USED_BYTES'])
        report['candidates'].append(record)
        atomic_json(a.output/f'initial-{words}-model.json',model)
        if best is None or search.energy(score) < best[0]:
            best = search.energy(score),search,model
    _,search,model = best
    report['initial'] = search.score(model)
    initial = (decode_fixed(model).astype(float)-128)/128
    for _ in range(a.proposals):
        search.step()
    model = search.export()
    packed = pack_tiny(model)
    exact = decode_fixed(unpack_tiny(packed))
    if not np.array_equal(exact,decode_fixed(model)):
        raise AssertionError('Packed integer projection changed PCM')
    audio = (exact.astype(float)-128)/128
    report.update(final=search.score(model),tiny_flash_data_bytes=len(packed['flash_data']),
                  eeprom_used_bytes=packed['constants']['EEPROM_USED_BYTES'],
                  config=search.config, improvements=search.improvements,
                  output_pcm_sha256=digest(exact.tobytes()), fits_tiny=False,
                  estoi=float(stoi(reference,audio,sr,extended=True)))
    atomic_json(a.output/'model.json',model)
    atomic_json(a.output/'quality.json',report)
    sf.write(a.output/'decoded.wav',audio,sr,subtype='PCM_16')
    matched_audio(a.output,dict(Original=reference,Initial=initial,Projected=audio),objective,
                  ('Original','Initial','Projected'))
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
