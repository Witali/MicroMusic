"""Reproduce the voiced-wave and unvoiced-noise limitation measurements."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[5]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from auto_encoder import SpectralObjective
from colored_period import decode_colored
from fixed_period import from_colored,decode_fixed
from period_wave import decode_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('noise-analysis.json'))
    args = parser.parse_args()
    path = ROOT/'ATtiny13A/Sound/research/period-balanced/vinni/model.json'
    source = json.loads(path.read_text(encoding='utf-8'))
    reference,sr = sf.read(args.reference)
    reference_hash = hashlib.sha256(args.reference.read_bytes()).hexdigest()
    if reference_hash!='749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03':
        raise ValueError('Reference differs from canonical Vinni audio')
    objective = SpectralObjective(reference,sr)
    full = decode_colored(source)
    base = deepcopy(source['base'])
    base['frames'] = [[p,i,g if v else 0,v] for p,i,g,v in base['frames']]
    voice = decode_model(base)
    fixed = from_colored(source)
    fixed['noise_filters'] = [[0]*8 for _ in range(3)]
    fixed['frames'] = [[p,h if h&128 else 0,0] for p,h,_ in fixed['frames']]
    fixed['dc_block_shift'] = 0
    integer = (decode_fixed(fixed).astype(float)-128)/128
    frames = np.asarray(source['base']['frames'])
    unvoiced = frames[(frames[:,2]>0)&(frames[:,3]==0)]
    sources = [Path(__file__)]+[CODEC/name for name in (
        'fixed_period.py','colored_period.py','period_wave.py','auto_encoder.py')]
    report = dict(schema='vinni-noise-analysis-v1',
        source_model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reference_sha256=reference_hash,
        source_sha256_normalized_lf={str(p.relative_to(ROOT)).replace('\\','/'):
            hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in sources},
        sample_rate=sr,samples=len(reference),active_unvoiced_frames=len(unvoiced),
        lowpass_unvoiced_frames=int(np.count_nonzero(unvoiced[:,1]<8)),
        unvoiced_index_counts={str(i):int(np.count_nonzero(unvoiced[:,1]==i)) for i in range(16)},
        float_full_metrics=dict(stoi=float(stoi(reference,full,sr)),**objective.spectrum(full)),
        float_voiced_only_stoi=float(stoi(reference,voice,sr)),
        integer_voiced_only_stoi=float(stoi(reference,integer,sr)),
        voiced_waveform_correlation=float(np.corrcoef(voice,integer)[0,1]),
        interpretation='The voiced waveform transfer is close for the retained pitch trajectory; this does not establish that the trajectory estimates the voice F0 correctly. The 37 low-pass frames do not identify consonants. The user identified door knocks in the source, so transient sound effects and pitch tracking must be investigated before attributing the quality gap to speech excitation. The new Vinni candidate remains an experiment, not an established improvement over the old HQ4 firmware.',
        hardware_verified=False)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
