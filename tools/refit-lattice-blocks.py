"""Escape single-coefficient minima with joint resonance and gain proposals.

The complete integer synthesis and unchanged STOI/spectral objective decide
each move. Decoder controls and storage precision do not change.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result);return result
fit=module('lattice_block_fit',ROOT/'tools/fit-mixed-lattice.py')
prior=module('lattice_block_source',ROOT/'tools/probe-q4-phase-wave.py')


def row_proposals(state,bits,row,source,families):
    """Yield independent stable vectors; never edit the supplied state."""
    old=state.coefficients[row].astype(np.int32);limit=(1<<bits.astype(np.int32))-1
    seen={(tuple(old),int(state.gains_q1[row]))}
    def emit(vector,scales,family):
        vector=np.asarray(vector,np.int16)
        if np.any(abs(vector.astype(np.int32))>limit):return
        for scale in scales:
            gain=int(np.clip(round(int(state.gains_q1[row])*scale),0,30));key=(tuple(vector),gain)
            if key not in seen:
                seen.add(key);yield family,vector.copy(),gain
    if 'pair' in families:
        for first,second in itertools.combinations(range(len(bits)),2):
            for a,b in itertools.product((-1,1),repeat=2):
                vector=old.copy();vector[first]+=a;vector[second]+=b
                yield from emit(vector,(.75,1.,1.25) if (first,second)==(0,1) else (1.,),'pair')
    if 'source' in families:
        target=np.rint(np.asarray(source)*2.**(bits.astype(int)-4))
        for blend in (.25,.5,.75,1.):
            yield from emit(np.clip(np.rint(old*(1-blend)+target*blend),-limit,limit),(.5,.75,1.,1.25,1.5),'source')
    if 'neighbor' in families:
        for neighbor in (row-1,row+1):
            if not 0<=neighbor<len(state.pitches):continue
            for blend in (.25,.5,1.):
                vector=np.rint(old*(1-blend)+state.coefficients[neighbor]*blend)
                yield from emit(vector,(.75,1.,1.25),'neighbor')


def run(reference_path,model_path,output,evaluations=18000,families=('pair','source','neighbor')):
    if evaluations<0 or not families or set(families)-{'pair','source','neighbor'}:raise ValueError('Invalid search configuration')
    start=time.perf_counter();state,bits,state_bits,mode,profile,zero_mean,meta=fit.load(model_path)
    x,sr=sf.read(reference_path,dtype='float64');reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if sr!=7500 or x.ndim!=1 or len(x)!=int(state.durations.sum()) or reference_hash!=meta['reference_sha256']:
        raise ValueError('Expected unchanged complete mono7500 original')
    step_policy=meta.get('step_policy','legacy');step_limit=fit.step_bound(x,step_policy)
    sources=(Path(__file__),ROOT/'tools/fit-mixed-lattice.py',ROOT/'tools/probe-q4-phase-wave.py',
        ROOT/'ATtiny13A/Sound/codec/mixed_lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py')
    source_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in sources}
    hints=prior.source_coefficients(x,state.durations,len(bits));spectral=fit.base.SpectrogramObjective(x)
    def score(candidate,detail=False):
        pcm,counts=fit.render(candidate,bits,state_bits,mode);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>step_limit):return None
        y=raw.astype(float)/128
        result=dict(stoi=float(fit.base.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            raw_rms=float(np.sqrt(np.mean(y*y))),peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),
            wrap_counts=counts.tolist(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
        if detail:result.update(estoi=fit.base.deterministic_estoi(x,y,7500),harmonic_metrics=fit.base.HarmonicTrackObjective(x).evaluate(y))
        return result
    def export(candidate):
        result=dict(meta,**candidate.fields());result.update(step_policy=step_policy,step_limit=step_limit,
            avr_implemented=False,serialized_format=False,hardware_tested=False)
        return result
    current=initial=score(state,True)
    if initial is None:raise ValueError('The seed must already pass integer guards')
    best=(initial['stoi'],state.copy());history=[];epochs=[];evaluated=valid=epoch=0
    output.mkdir(parents=True,exist_ok=True);fit.base.save(output/'initial-model.json',export(state))
    while evaluated<evaluations:
        accepted=0
        for row in (range(len(state.pitches)) if epoch%2==0 else range(len(state.pitches)-1,-1,-1)):
            for family,coefficients,gain in row_proposals(state,bits,row,hints[row],families):
                if evaluated>=evaluations:break
                candidate=state.copy();candidate.coefficients[row]=coefficients;candidate.gains_q1[row]=gain
                evaluated+=1;q=score(candidate)
                if q is not None:
                    valid+=1
                    if fit.base.energy(q)<fit.base.energy(current)-1e-12:
                        state,current=candidate,q;accepted+=1
                        history.append(dict(evaluation=evaluated,row=row,family=family,coefficients=coefficients.tolist(),gain=gain,
                            stoi=q['stoi'],spectrogram_loss=q['spectrogram_loss'],pcm_sha256=q['pcm_sha256']))
                        if q['stoi']>best[0] and q['spectrogram_loss']<=.4848481735668308 and abs(q['raw_mean'])<=.07764022651760058:
                            best=(q['stoi'],state.copy())
                if evaluated%250==0:
                    progress=dict(evaluated=evaluated,valid=valid,accepted=len(history),score=current,elapsed_seconds=time.perf_counter()-start)
                    fit.base.save(output/'progress.json',progress);fit.base.save(output/'checkpoint.json',export(state));print(json.dumps(progress),flush=True)
            if evaluated>=evaluations:break
        epochs.append(dict(epoch=epoch,evaluated=evaluated,accepted=accepted));epoch+=1
        if not accepted:break
    final=score(state,True);best_detail=score(best[1],True);fit.validate(state,bits,state_bits,zero_mean)
    fit.base.save(output/'model.json',export(state));fit.base.save(output/'best-intelligibility-model.json',export(best[1]))
    pcm,_=fit.render(state,bits,state_bits,mode);sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report=dict(schema='lattice-block-study-v1',initial=initial,final=final,best_intelligibility=best_detail,evaluated=evaluated,
        valid=valid,accepted=len(history),history=history,epochs=epochs,families=list(families),step_policy=step_policy,step_limit=step_limit,
        reference_sha256=reference_hash,seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),source_sha256_normalized_lf=source_hashes,
        elapsed_seconds=time.perf_counter()-start,avr_implemented=False,serialized_format=False,hardware_tested=False)
    fit.base.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--evaluations',type=int,default=18000)
    p.add_argument('--families',nargs='+',choices=('pair','source','neighbor'),default=('pair','source','neighbor'))
    a=p.parse_args();run(a.reference,a.model,a.output,a.evaluations,a.families)
