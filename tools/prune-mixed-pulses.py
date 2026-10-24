"""Measure literal/derived waveform merges with the full integer teacher.

Physical compaction is lossless; each preceding merge is lossy and measured.
The result is a waveform budget, not the size of a complete AVR image.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mixed_pulse_pruner',ROOT/'tools/fit-mixed-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


def active(state):return np.unique(state.modes[(state.pitches>0)&(state.gains_q1>0)])


def compact(state,bits,state_bits,mode):
    before,counts=fit.render(state,bits,state_bits,mode);used=active(state);result=state.copy()
    book=np.zeros_like(state.waves_q1);mapping={int(old):new for new,old in enumerate(used)}
    for old,new in mapping.items():book[new]=state.waves_q1[old]
    result.modes=np.asarray([mapping.get(int(value),0) for value in state.modes],np.int16);result.waves_q1=book
    after,new_counts=fit.render(result,bits,state_bits,mode)
    np.testing.assert_array_equal(before,after);np.testing.assert_array_equal(counts,new_counts)
    return result


def storage(state):
    count=len(active(state));head_width=16 if state.tail_policy=='balance16' else state.waves_q1.shape[1]
    packed=(count*head_width*(state.wave_fraction_bits+3)+7)//8
    descriptors=count*(1 if state.wave_fraction_bits==1 else 2) if state.tail_policy=='balance16' else 0
    return dict(forms=count,packed_waveform_bytes=packed,area_descriptor_bytes=descriptors,waveforms_fit_eeprom=packed<=64)


def run(reference_path,model_path,output,minimum_forms=1):
    if not 1<=minimum_forms<=8:raise ValueError('Expected one through eight forms')
    start=time.perf_counter();state,bits,state_bits,mode,profile,zero_mean,meta=fit.load(model_path)
    x,sr=sf.read(reference_path,dtype='float64');reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if sr!=7500 or x.ndim!=1 or len(x)!=int(state.durations.sum()) or reference_hash!=meta['reference_sha256']:
        raise ValueError('Expected unchanged complete mono7500 original')
    step_policy=meta.get('step_policy','legacy');step_limit=fit.step_bound(x,step_policy)
    spectral=fit.base.SpectrogramObjective(x);evaluated=0;records=[];history=[]
    def score(candidate):
        nonlocal evaluated
        evaluated+=1;pcm,counts=fit.render(candidate,bits,state_bits,mode);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>step_limit):return None
        y=raw.astype(float)/128
        return dict(stoi=float(fit.base.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            raw_rms=float(np.sqrt(np.mean(y*y))),peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),
            wrap_counts=counts.tolist(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
    output.mkdir(parents=True,exist_ok=True)
    while True:
        state=compact(state,bits,state_bits,mode);used=active(state);count=len(used)
        if not count:raise ValueError('No active voiced form')
        q=score(state)
        if q is None:raise ValueError('Starting model violates the integer guards')
        saved=dict(meta,**state.fields(),maximum_forms=count,avr_implemented=False,serialized_format=False,hardware_tested=False)
        fit.base.save(output/str(count)/'model.json',saved)
        record=dict(**storage(state),score=q,model=f'{count}/model.json');records.append(record);print(json.dumps(record),flush=True)
        if count<=minimum_forms:break
        best=None
        for source in used:
            for target in used:
                if source==target:continue
                candidate=state.copy();candidate.modes[candidate.modes==source]=target;q=score(candidate)
                if q is not None and (best is None or fit.base.energy(q)<best[0]):
                    best=(fit.base.energy(q),candidate,dict(source=int(source),target=int(target),score=q))
        if best is None:break
        _,state,step=best;history.append(step)
    sources=(Path(__file__),ROOT/'tools/fit-mixed-lattice.py',ROOT/'ATtiny13A/Sound/codec/mixed_lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py')
    report=dict(schema='mixed-pulse-prune-v1',records=records,merges=history,evaluated=evaluated,
        reference_sha256=reference_hash,seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in sources},
        elapsed_seconds=time.perf_counter()-start,avr_implemented=False,serialized_format=False,hardware_tested=False,
        scope='Every physical remap preserves PCM exactly; merges are measured losses; waveform bytes exclude speech, decoder, EOF and alignment')
    fit.base.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--minimum-forms',type=int,default=1);a=p.parse_args()
    run(a.reference,a.model,a.output,a.minimum_forms)
