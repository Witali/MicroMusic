"""Automatically adapt the retained Vinni model's scales to fixed arithmetic.

The original clip has different global base/residual scales from Chego. Test a
small deterministic scale grid before exact output refinement; no frame or
phoneme is selected manually. Bound FIR accumulators by the integer contract.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from fixed_period import from_colored, integer_noise
from fixed_search import FixedSearch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,default=ROOT.parents[1]/'build/hq4-preview/vinni/original.wav')
    parser.add_argument('--output',type=Path,default=ROOT/'build/tiny-speech/vinni/prepared')
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True,exist_ok=True)
    path = ROOT/'ATtiny13A/Sound/research/period-balanced/vinni/model.json'
    source = json.loads(path.read_text(encoding='utf-8'))
    # Worktree layout: repository/.worktree/speech-quality, so external audio
    # belongs to the primary checkout's ignored build directory.
    reference_path = args.reference
    reference,sr = sf.read(reference_path)
    reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if reference_hash!='749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03':
        raise ValueError('Vinni reference hash differs from the retained manifest')
    scorer = object.__new__(FixedSearch)
    scorer.objective = SpectralObjective(reference,sr)
    initial = from_colored(source)
    initial['dc_block_shift'] = 7
    filters = np.asarray(initial['noise_filters'],dtype=int)
    safe = filters.copy()
    for i in range(3):
        l1 = 2*abs(safe[i,:7]).sum()+abs(safe[i,7])
        if l1>17:
            safe[i] = np.rint(safe[i]*17/l1).astype(int)
        while 2*abs(safe[i,:7]).sum()+abs(safe[i,7])>17:
            k = int(np.argmax(abs(safe[i])))
            safe[i,k] -= np.sign(safe[i,k])
    initial['noise_filters'] = safe.tolist()
    original_norm = np.sqrt(2*(filters[:,:7]**2).sum(axis=1)+filters[:,7]**2)
    safe_norm = np.sqrt(2*(safe[:,:7]**2).sum(axis=1)+safe[:,7]**2)
    color_ratio = np.r_[1.,original_norm/np.maximum(safe_norm,1e-12)]
    levels = np.asarray([0,1/32,1/16,1/8,1/4,1/2,3/4,1])
    base_ratio = source['base']['scale_u16']/65535*8/7
    residual_ratio = source['scale_u16']/13296
    candidates,best,white_candidates,white_best = [],None,[],None
    white_unit_rms = float(np.std(integer_noise(source['base']['samples'],0xace1,safe)[0]/128/64))
    for output_gain in (.7,.85,1.,1.15,1.3,1.5,1.75,1.85,2.,2.25,2.5):
        for noise_gain in (.75,1.,1.25):
            model = deepcopy(initial)
            for frame,old in zip(model['frames'],source['base']['frames']):
                gain = int(np.argmin(abs(levels-levels[old[2]]*base_ratio*output_gain)))
                frame[1] = (frame[1] & 143) | gain << 4
                color,level = frame[2] >> 4,frame[2] & 15
                level = int(np.clip(np.rint(level*residual_ratio*output_gain*noise_gain*color_ratio[color]),0,15))
                frame[2] = color << 4 | level
            score = scorer.score(model)
            feasible = score['peak']<=.95 and score['clips']==score['pre_dc_clips']==0
            energy = score['loss']+8*(1-score['stoi'])
            candidates.append(dict(output_gain=output_gain,noise_gain=noise_gain,feasible=feasible,**score))
            if feasible and (best is None or energy<best[0]):
                best = energy,model,candidates[-1]
            white = deepcopy(model)
            white['noise_filters'] = [[0]*8 for _ in range(3)]
            for frame,old,original_code in zip(white['frames'],source['base']['frames'],source['gains']):
                color,level = original_code >> 4,original_code & 15
                noise_norm = original_norm[color-1]/8 if color else 1.
                residual_rms = level/15*source['scale_u16']/65535*output_gain*noise_gain*noise_norm
                unvoiced_rms = 0.
                if not old[3]:
                    frame[1] &= 143
                    unvoiced_rms = levels[old[2]]*source['base']['scale_u16']/65535*output_gain
                frame[2] = int(np.clip(np.rint(np.hypot(residual_rms,unvoiced_rms)/white_unit_rms),0,15))
            white_score = scorer.score(white)
            feasible = white_score['peak']<=.95 and white_score['clips']==white_score['pre_dc_clips']==0
            energy = white_score['loss']+8*(1-white_score['stoi'])
            white_candidates.append(dict(output_gain=output_gain,noise_gain=noise_gain,feasible=feasible,**white_score))
            if feasible and (white_best is None or energy<white_best[0]):
                white_best = energy,white,white_candidates[-1]
    if best is None:
        raise RuntimeError('No scale candidate meets the integer peak/saturation bounds')
    report = dict(schema='vinni-fixed-preparation-v1',source_model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  reference_sha256=reference_hash,source_base_scale_u16=source['base']['scale_u16'],
                  source_residual_scale_u16=source['scale_u16'],original_filters=filters.tolist(),
                  safe_filters=safe.tolist(),selected=best[2],candidates=candidates,
                  white_selected=white_best[2],white_candidates=white_candidates,
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for name,value in (('model.json',best[1]),('white-model.json',white_best[1]),('quality.json',report)):
        (output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(colored=best[2],white=white_best[2]),indent=2))


if __name__=='__main__':main()
