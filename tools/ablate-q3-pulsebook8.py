"""Remove new forms while keeping fitted timing/filter data, then refit selectors.

This is a bounded greedy ablation, not a globally optimal four-form encoder.
It tests whether the observed gain survives removal of the extra source forms.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('eight_ablation_search',ROOT/'tools/probe-q3-pulsebook8.py')
probe=importlib.util.module_from_spec(spec);sys.modules[spec.name]=probe;spec.loader.exec_module(probe)


def run(reference_path,model_path,output):
    reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected canonical mono7500 reference')
    f,d,b,_=probe.builder.load_model(model_path)
    objective=probe.search.Objective(reference,floor_budget=673,rounded_budget=673)
    state=probe.search.State(f,d,b,False,1);state.score=objective.evaluate(state)
    if state.score is None:raise ValueError('Eight-form input fails guards')
    initial=probe.extra_metrics(state,objective);history=[];evaluated=0
    for index in np.flatnonzero((state.frames[:,1]>>4)>=4):
        original_gain=int(state.frames[index,1])&15;best=None
        for mode in range(4):
            for gain in sorted({max(0,original_gain-1),original_gain,min(15,original_gain+1)}):
                trial=probe.search.State(state.frames.copy(),d,b,False,1)
                trial.frames[index,1]=(mode<<4)|gain;trial.score=objective.evaluate(trial);evaluated+=1
                if trial.score is not None and (best is None or objective.energy(trial.score)<objective.energy(best.score)):
                    best=trial
        if best is None:raise ValueError('No guard-safe four-form replacement at frame '+str(index))
        history.append(dict(frame=int(index),old_selector=int(state.frames[index,1])>>4,
            new_selector=int(best.frames[index,1])>>4,new_gain=int(best.frames[index,1])&15))
        state=best
    assert np.all(state.frames[:,1]<64)
    final=probe.extra_metrics(state,objective)
    value=json.loads(Path(model_path).read_text(encoding='utf-8'))
    value.update(schema='hq4-q3-pulsebook-v1',frames=state.frames.tolist(),pulsebook=b[:4].tolist(),stream_budget=673)
    probe.save(output/'model.json',value);probe.save(output/'quality.json',final)
    report=dict(schema='q3-pulsebook8-ablation-v1',input_model_sha256=probe.sha(model_path),
        before=initial,after=final,evaluated=evaluated,history=history,
        policy='All fitted pitches/durations/coefficients and first four forms fixed; each upper selector replaced with the best lower selector and gain +/-1 by exact full-clip objective; greedy order',
        source_sha256_normalized_lf=probe.hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest())
    probe.save(output/'report.json',report)
    print(json.dumps(dict(before={k:initial[k] for k in ('stoi','estoi','spectrogram_loss')},
        after={k:final[k] for k in ('stoi','estoi','spectrogram_loss')},evaluated=evaluated)))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','model','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.reference,a.model,a.output)
