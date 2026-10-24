"""Measure waveform-count tradeoffs through the complete product decoder.

Every merge is selected by original-versus-integer-output error. Used rows are
then remapped exactly; freed EEPROM is only a data-layout budget remainder.
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
spec=importlib.util.spec_from_file_location('product_form_pruner',ROOT/'tools/fit-q4-product233.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


def active(s):
    expanded=fit.expand(s)
    return np.unique(expanded.modes[(expanded.pitches>0)&(expanded.gains_q1>0)])


def compact(s,bits,nearest):
    before,counts=fit.render(s,bits,nearest);result=s.copy();used=active(s);book=np.zeros_like(s.waves_q1)
    mapping={int(old):n for n,old in enumerate(used)}
    for old,new in mapping.items():book[new]=s.waves_q1[old]
    result.root[:,2]=[mapping.get(int(value),0) for value in result.root[:,2]];result.waves_q1=book
    after,new_counts=fit.render(result,bits,nearest)
    np.testing.assert_array_equal(before,after);np.testing.assert_array_equal(counts,new_counts)
    return result


def run(reference_path,model_path,output):
    meta=json.loads(model_path.read_text(encoding='utf-8'));state=fit.from_model(meta)
    bits,nearest=meta['state_bits'],meta['nearest'];x,sr=sf.read(reference_path,dtype='float64')
    reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if sr!=7500 or x.ndim!=1 or len(x)!=int(state.durations.sum()) or reference_hash!=meta['reference_sha256']:
        raise ValueError('Expected unchanged complete mono7500 original')
    spectral=fit.fit.SpectrogramObjective(x);records=[];history=[];evaluated=0
    def score(s):
        nonlocal evaluated
        evaluated+=1;pcm,counts=fit.render(s,bits,nearest);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>=48):return None
        y=raw.astype(float)/128
        return dict(stoi=float(fit.fit.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
    output.mkdir(parents=True,exist_ok=True)
    while True:
        state=compact(state,bits,nearest);used=active(state);count=len(used)
        if not count:raise ValueError('No voiced waveform to prune')
        q=score(state)
        if q is None:raise ValueError('Starting layout violates integer guards')
        saved=dict(meta,**state.fields(),maximum_forms=count)
        # A v1 input keeps no phase fields; both tables stay exactly byte-sized.
        if meta['schema']==fit.codec.SCHEMA:saved.pop('attack_flags',None);saved.pop('hold_flags',None)
        fit.fit.save(output/str(count)/'model.json',saved)
        payload=fit.codec.pack_frames(state.pitches,state.local_gains,state.durations,state.indices,state.halves)
        last=np.flatnonzero(np.any(state.waves_q1[used]!=0,axis=0))
        width=next(n for n in (4,8,16) if not len(last) or n>int(last[-1]));wave_bytes=count*width//2
        record=dict(forms=count,score=q,table_bytes=96,stream_bytes=len(payload),data_bytes=96+len(payload),
            waveform_bytes=wave_bytes,maximum_code_bytes_before_alignment=1024-(96+len(payload))+64-wave_bytes-1)
        records.append(record);print(json.dumps(record),flush=True)
        if count==1:break
        best=None
        for source in used:
            for target in used:
                if source==target:continue
                candidate=state.copy();candidate.root[candidate.root[:,2]==source,2]=target
                score_value=score(candidate)
                if score_value is not None and (best is None or fit.fit.energy(score_value)<best[0]):
                    best=(fit.fit.energy(score_value),candidate,dict(source=int(source),target=int(target),score=score_value))
        if best is None:break
        _,state,step=best;history.append(step)
    report=dict(schema='q4-product-form-prune-v1',records=records,merges=history,exact_evaluations=evaluated,
        reference_sha256=reference_hash,seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
            for p in (Path(__file__),ROOT/'tools/fit-q4-product233.py',ROOT/'ATtiny13A/Sound/codec/q4_product233.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py')},
        avr_implemented=False,policy='Exact PCM-preserving physical remap; merges are lossy and measured; code capacity is a remainder, not a complete-image fit')
    fit.fit.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();run(a.reference,a.model,a.output)
