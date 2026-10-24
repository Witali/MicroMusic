"""Propose whole pulse shapes by fitting forward synthesis responses.

The floating linear system only suggests a joint move. The original, unchanged
reference and complete integer decoder decide every accepted candidate.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from numba import njit
from scipy.optimize import minimize
from scipy.signal import stft,istft
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pulse_output_fit_api',ROOT/'tools/fit-mixed-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


@njit(cache=True)
def floating_filter(excitation,rows,coefficients,bits):
    states=np.zeros(coefficients.shape[1],np.float64);output=np.empty(len(rows),np.float64);previous=0.
    for n in range(len(rows)):
        ex=excitation[n]/512.
        for j in range(len(states)-1,-1,-1):
            k=coefficients[rows[n],j]/(1<<bits[j]);old=states[j];ex-=old*k
            if j<len(states)-1:states[j+1]=old+ex*k
        states[0]=ex;previous=ex+previous*.5;output[n]=previous
    return output


def excitation(s,waves,phase_mode):
    rows,values=fit.phase.legacy_excitation(s.pitches,s.gains_q1,s.durations,s.modes,waves,s.quarters,
        pitch_bits=2,phase_mode=phase_mode,phase_modes=s.phase_modes,pulse_width=waves.shape[1])
    values[s.pitches[rows]==0]*=2
    return rows,values


def responses(s,bits,phase_mode):
    modes=np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)])
    coordinates=[(int(mode),tap) for mode in modes for tap in range(s.waves_q1.shape[1])]
    zeros=np.zeros_like(s.waves_q1);rows,noise=excitation(s,zeros,phase_mode)
    offset=floating_filter(noise,rows,s.coefficients,bits)
    matrix=np.empty((len(rows),len(coordinates)),float)
    for column,(mode,tap) in enumerate(coordinates):
        impulse=zeros.copy();impulse[mode,tap]=1
        _,values=excitation(s,impulse,phase_mode)
        matrix[:,column]=floating_filter(values-noise,rows,s.coefficients,bits)
    current=np.asarray([s.waves_q1[m,t] for m,t in coordinates],float)
    _,values=excitation(s,s.waves_q1,phase_mode)
    actual=floating_filter(values,rows,s.coefficients,bits)
    error=float(abs(matrix@current+offset-actual).max())
    if error>1e-11:raise AssertionError('Forward basis fails linear reconstruction')
    return matrix,offset,current,coordinates,error


def phase_target(reference,candidate,size):
    _,_,x=stft(reference,fs=7500,nperseg=size,noverlap=size-size//8)
    _,_,y=stft(candidate,fs=7500,nperseg=size,noverlap=size-size//8)
    phase=np.exp(1j*np.angle(y))
    _,target=istft(abs(x)*phase,fs=7500,nperseg=size,noverlap=size-size//8)
    return target[:len(reference)]


def run(reference_path,model_path,output,pulse_length=32,seed=20261024):
    started=time.perf_counter();state,bits,state_bits,phase_mode,profile,zero_mean,meta=fit.load(model_path,pulse_length=pulse_length)
    x,sr=sf.read(reference_path,dtype='float64');reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if sr!=7500 or x.ndim!=1 or len(x)!=int(state.durations.sum()) or reference_hash!=meta['reference_sha256']:
        raise ValueError('Expected the unchanged complete mono7500 original')
    paths=(Path(__file__),ROOT/'tools/fit-mixed-lattice.py',ROOT/'ATtiny13A/Sound/codec/mixed_lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py')
    sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in paths}
    spectral=fit.base.SpectrogramObjective(x);evaluations=0;valid=0;history=[];seen=set();rng=np.random.default_rng(seed)
    def score(s,detail=False):
        pcm,counts=fit.render(s,bits,state_bits,phase_mode);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>=48):return None
        y=raw.astype(float)/128
        q=dict(stoi=float(fit.base.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            raw_rms=float(np.sqrt(np.mean(y*y))),peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),
            wrap_counts=counts.tolist(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
        if detail:q.update(estoi=fit.base.deterministic_estoi(x,y,7500),harmonic_metrics=fit.base.HarmonicTrackObjective(x).evaluate(y))
        return q
    def export(s):
        extended=s.waves_q1.shape[1]!=16 or s.phase_modes is not None
        return dict(schema=fit.codec.PULSE_SCHEMA if extended else fit.codec.SCHEMA,
            **(dict(pulse_length=int(s.waves_q1.shape[1])) if extended else {}),
            sample_rate=7500,coefficient_bits=bits.tolist(),state_bits=state_bits,nearest=True,precision_profile=profile,
            zero_mean=zero_mean,phase_mode=phase_mode,**s.fields(),reference_sha256=reference_hash,
            avr_implemented=False,serialized_format=False,hardware_tested=False)
    initial=best=score(state,True)
    if initial is None:raise ValueError('Integer seed violates guards')
    output.mkdir(parents=True,exist_ok=True);fit.base.save(output/'initial-model.json',export(state))
    matrix,offset,old,coordinates,reconstruction=responses(state,bits,phase_mode)
    gram=matrix.T@matrix;scale=max(float(np.trace(gram)/len(old)),1e-20)
    current=matrix@old+offset;targets={'waveform':x}
    targets.update({f'phase-{size}':phase_target(x,current,size) for size in (256,512,1024)})
    best_state=state.copy();best_config=None;solves=[]
    for name,target in targets.items():
        for amplitude in (.5,.625,.75,1.):
            rhs=matrix.T@(target*amplitude-offset)
            for regularization in (1e-4,.001,.01,.1,1.):
                ridge=regularization*scale;normal=gram+ridge*np.eye(len(old));linear=rhs+ridge*old
                start=np.clip(np.linalg.solve(normal,linear),-7,7)
                objective=lambda w:(float(.5*w@(normal@w)-linear@w),normal@w-linear)
                solved=minimize(objective,start,jac=True,method='L-BFGS-B',bounds=[(-7,7)]*len(old),
                    options=dict(maxiter=1000,ftol=1e-12,gtol=1e-10))
                solves.append(dict(target=name,amplitude=amplitude,regularization=regularization,success=bool(solved.success),iterations=int(solved.nit)))
                for amount in (.25,.5,.75,1.):
                    value=old+(solved.x-old)*amount
                    quantizations=[np.rint(value)]
                    quantizations.extend(np.floor(value)+(rng.random(len(value))<value-np.floor(value)) for _ in range(3))
                    for rounding,wave in enumerate(quantizations):
                        candidate=state.copy()
                        for (mode,tap),v in zip(coordinates,wave):candidate.waves_q1[mode,tap]=int(np.clip(v,-7,7))
                        if zero_mean:candidate.waves_q1=fit.zero_area(candidate.waves_q1)
                        signature=candidate.waves_q1.tobytes()
                        if signature in seen:continue
                        seen.add(signature);evaluations+=1;q=score(candidate)
                        if q is not None:
                            valid+=1
                            if fit.base.energy(q)<fit.base.energy(best)-1e-12:
                                best,best_state=q,candidate
                                best_config=dict(target=name,amplitude=amplitude,regularization=regularization,amount=amount,rounding=rounding)
                                history.append(dict(evaluated=evaluations,configuration=best_config,score=q))
                                print(json.dumps(history[-1]),flush=True)
                        if evaluations%50==0:
                            fit.base.save(output/'progress.json',dict(evaluated=evaluations,valid=valid,best=best,elapsed_seconds=time.perf_counter()-started))
    fit.validate(best_state,bits,state_bits,zero_mean);final=score(best_state,True)
    fit.base.save(output/'model.json',export(best_state));pcm,_=fit.render(best_state,bits,state_bits,phase_mode)
    sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report=dict(schema='pulse-output-refit-v1',initial=initial,final=final,evaluated=evaluations,valid=valid,history=history,
        best_configuration=best_config,solves=solves,linear_reconstruction_error=reconstruction,variables=len(old),seed=seed,
        source_sha256_normalized_lf=sources,reference_sha256=reference_hash,seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        elapsed_seconds=time.perf_counter()-started,avr_implemented=False,serialized_format=False,hardware_tested=False,
        policy='Floating responses propose joint waveform moves; unchanged original and exact integer output select the final model')
    fit.base.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--pulse-length',type=int,choices=(16,32),default=32);p.add_argument('--seed',type=int,default=20261024)
    a=p.parse_args();run(a.reference,a.model,a.output,a.pulse_length,a.seed)
