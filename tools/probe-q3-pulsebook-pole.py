"""Bounded new-format pulsebook study with an extra stable -15/16 coefficient.

Seed masks and gain scales are automatic proposals, never decoder side input.
The unchanged reference, absolute targets and complete AVR capacities remain
explicit. No public profile is modified or reinterpreted.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook_pole as codec

spec=importlib.util.spec_from_file_location('pulsebook_pole_search',ROOT/'tools/probe-q3-pulsebook.py')
search=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=search
spec.loader.exec_module(search)
search.render,search.validate,search.SCHEMA=codec.render,codec.validate,codec.SCHEMA


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--model',required=True,type=Path,action='append')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--proposals',type=int,default=6000)
    p.add_argument('--seed',type=int,default=23311)
    p.add_argument('--extra-seed-directory',type=Path)
    a=p.parse_args()
    reference,sr=sf.read(a.reference,dtype='float64')
    if sr!=7500 or reference.ndim!=1 or a.proposals<0:
        p.error('Expected unchanged mono7500Hz source and nonnegative proposals')
    objective=search.Objective(reference,rounded_budget=589,floor_budget=593)
    seeds=[];trials=[]
    for path in a.model:
        model=json.loads(path.read_text(encoding='utf-8'))
        nearest=bool(model.get('nearest',model.get('schema')=='hq4-q3-rounded-v1'))
        f,d=np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16)
        book=np.asarray(model.get('pulsebook',codec.legacy_tables()),np.int8)
        f,reuse=search.fit_budget(f,d,589 if nearest else 593)
        for mask in (0,1,3,15,255):
            for gain_scale in ((1.,) if not mask else (.65,.85,1.)):
                trial=f.copy()
                for coefficient in range(8):
                    if mask & (1<<coefficient):
                        column=2+coefficient//2;shift=(coefficient%2)*4
                        selected=((trial[:,column]>>shift)&15)==1
                        trial[selected,column]&=np.uint8(255^(15<<shift))
                trial[:,1]=(trial[:,1]&48)|np.minimum(15,np.rint((trial[:,1]&15)*gain_scale)).astype(np.uint8)
                state=search.State(trial,d.copy(),book.copy(),nearest,1)
                state.score=objective.evaluate(state)
                trials.append(dict(source_sha256=search.sha(path),mask=mask,gain_scale=gain_scale,nearest=nearest,
                    coefficient_reuse=reuse,score=state.score))
                if state.score is not None:
                    seeds=search.pareto_add(seeds,state)
    if not seeds:
        raise ValueError('No clean extended-pole seed under actual 1KB capacities')
    selected=[min(seeds,key=lambda state:objective.energy(state.score)),
        max(seeds,key=lambda state:state.score['stoi']),min(seeds,key=lambda state:state.score['spectrogram_loss'])]
    selected+=sorted(seeds,key=lambda state:objective.energy(state.score))[:5]
    paths=[];seen=set()
    for state in selected:
        fingerprint=(state.frames.tobytes(),state.durations.tobytes(),state.book.tobytes(),state.nearest)
        if fingerprint in seen: continue
        seen.add(fingerprint)
        folder=a.output/'initial'/str(len(paths))
        search.export_state(folder,state,objective,search.sha(a.reference))
        paths.append(folder/'model.json')
    search.save(a.output/'seed-screen.json',dict(schema='pulsebook-pole-seeds-v1',trials=trials))
    result=search.run(a.reference,paths,a.output,proposals=a.proposals,seed=a.seed,
        extra_seed_directory=a.extra_seed_directory,rounded_budget=589,floor_budget=593)
    result['schema']='q3-pulsebook-pole-search-v1'
    result['format']=codec.SCHEMA
    result['new_coefficient']='Packed nibble0 means -15/16; other signed nibble values retain c/8'
    for path in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q3_pulsebook_pole.py'):
        result['source_sha256_normalized_lf'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    search.save(a.output/'report.json',result)
    print(json.dumps(dict(target_met=result['target_met'],finalists=result['finalists'])))


if __name__=='__main__': main()
