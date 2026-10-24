"""Refine quarter-sample periods without reinterpreting old half-pitch models.

The explicitly tagged new schema stores quarters. Even quarter flags reproduce
the entire half-pitch control. Decoder, Flash fit and timing are unimplemented.
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
spec=importlib.util.spec_from_file_location('quarter_lattice_api',ROOT/'tools/refine-q4-lattice.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)
import q4_sparse_stream as stream

SCHEMA='q4-quarter-fit-v1'


def load(path):
    model=json.loads(path.read_text(encoding='utf-8'))
    if model['schema']==base.SCHEMA:
        state=base.load(path);state.halves*=2
    elif model['schema']==SCHEMA:
        state=base.State(*(np.asarray(model['quarters' if name=='halves' else name],np.int16)
            for name in base.State.__annotations__))
    else:raise ValueError('Expected tagged Q4 lattice or quarter-period model')
    validate(state);return state,model


def validate(state):
    if state.halves.dtype.kind not in 'iu' or np.any(state.halves<0) or np.any(state.halves>3):
        raise ValueError('Quarter flags must be integer values in 0..3')
    control=state.copy();control.halves=(control.halves!=0).astype(np.int16);base.validate(control)


def render(state,bits,nearest,phase_mode=0):
    rows,excitation=base.codec.legacy_excitation(state.pitches,state.gains_q1,state.durations,
        state.modes,state.waves_q1,state.halves,pitch_bits=2,phase_mode=phase_mode)
    excitation[state.pitches[rows]==0]*=2
    return base.codec.filter_signal(excitation,rows,state.coefficients,state_bits=bits,nearest=nearest,fraction_bits=2)


def apply(state,action):
    if action[0]!='pitch':return base.apply(state,action)
    _,row,_,delta=action;candidate=state.copy()
    value=int(candidate.pitches[row])*4+int(candidate.halves[row])+delta
    if not 4<=value<=507:return None
    candidate.pitches[row]=value//4;candidate.halves[row]=value%4;return candidate


def run(reference_path,model_path,output,evaluations=12000,phase_mode=None):
    if evaluations<0:raise ValueError('Expected nonnegative evaluation budget')
    start=time.perf_counter();state,meta=load(model_path);bits,nearest=meta['state_bits'],meta['nearest']
    phase_mode=meta.get('phase_mode',0) if phase_mode is None else phase_mode
    if phase_mode not in (0,1,2):raise ValueError('Expected reset, continuous-delayed or continuous-immediate phase mode')
    x,sr=sf.read(reference_path,dtype='float64');reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if sr!=7500 or x.ndim!=1 or len(x)!=int(state.durations.sum()) or reference_hash!=meta['reference_sha256']:
        raise ValueError('Expected unchanged complete mono7500 original')
    source_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
        for p in (Path(__file__),ROOT/'tools/refine-q4-lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py',ROOT/'ATtiny13A/Sound/codec/q4_sparse_stream.py')}
    spectral=base.SpectrogramObjective(x);history=[];epochs=[];evaluated=0
    def score(s,detail=False):
        pcm,counts=render(s,bits,nearest,phase_mode);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>=48):return None
        y=raw.astype(float)/128;q=dict(stoi=float(base.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),wrap_counts=counts.tolist(),
            pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
        if detail:q.update(estoi=base.deterministic_estoi(x,y,7500),harmonic_metrics=base.HarmonicTrackObjective(x).evaluate(y))
        return q
    def export(s):
        fields=s.fields();fields['quarters']=fields.pop('halves')
        return dict(schema=SCHEMA,sample_rate=7500,state_bits=bits,nearest=nearest,pitch_bits=2,phase_mode=phase_mode,
            **fields,reference_sha256=reference_hash,avr_implemented=False,hardware_tested=False)
    initial=current=score(state,True);guard_screen=[];seed_scale=1.
    if initial is None:
        original_gains=state.gains_q1.copy()
        for scale in (.875,.75,.625,.5):
            state.gains_q1=np.where(original_gains>0,np.maximum(1,np.floor(original_gains*scale)),0).astype(np.int16)
            trial_pcm,trial_counts=render(state,bits,nearest,phase_mode);raw=trial_pcm.astype(np.int16)-128
            guard_screen.append(dict(scale=scale,counts=trial_counts.tolist(),peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max())))
            initial=current=score(state,True)
            if initial is not None:seed_scale=scale;break
    if initial is None:raise ValueError('Initial quarter-period model fails integer guards after seed gain screening')
    best_stoi=(initial['stoi'],state.copy(),initial);output.mkdir(parents=True,exist_ok=True)
    base.save(output/'initial-model.json',export(state));print(json.dumps(dict(evaluated=0,score=initial)),flush=True)
    epoch=0
    while evaluated<evaluations:
        accepted=0
        if epoch==0:
            proposals=[('pitch',int(row),0,delta) for row in np.flatnonzero(state.pitches) for delta in (-1,1)]
        else:
            proposals=list(base.actions(state))
            if epoch%2==0:proposals.reverse()
        for action in proposals:
            if evaluated>=evaluations:break
            candidate=apply(state,action)
            if candidate is None:continue
            evaluated+=1;q=score(candidate)
            if q is not None and base.energy(q)<base.energy(current)-1e-12:
                state,current=candidate,q;accepted+=1
                history.append(dict(evaluation=evaluated,action=list(action),stoi=q['stoi'],spectrogram_loss=q['spectrogram_loss'],pcm_sha256=q['pcm_sha256']))
                if q['stoi']>best_stoi[0] and q['spectrogram_loss']<=.4848481735668308 and abs(q['raw_mean'])<=.07764022651760058:
                    best_stoi=(q['stoi'],state.copy(),q)
            if evaluated%250==0:
                progress=dict(evaluated=evaluated,accepted=len(history),score=current,elapsed_seconds=time.perf_counter()-start)
                base.save(output/'progress.json',progress);base.save(output/'checkpoint.json',export(state));print(json.dumps(progress),flush=True)
        epochs.append(dict(epoch=epoch,evaluated=evaluated,accepted=accepted,score=current));epoch+=1
        if not accepted and epoch>1:break
    payload=stream.pack(state.pitches,state.gains_q1,state.durations,state.coefficients,state.modes,state.halves,pitch_bits=2)
    for expected,got in zip((state.pitches,state.gains_q1,state.durations,state.coefficients,state.modes,state.halves),stream.unpack(payload,pitch_bits=2)):
        np.testing.assert_array_equal(expected,got)
    final=score(state,True);best_detail=score(best_stoi[1],True)
    base.save(output/'model.json',export(state));base.save(output/'best-intelligibility-model.json',export(best_stoi[1]))
    pcm,_=render(state,bits,nearest,phase_mode);sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report=dict(schema='q4-quarter-fit-study-v1',initial=initial,final=final,best_intelligibility=best_detail,
        evaluated=evaluated,accepted=len(history),history=history,epochs=epochs,stream_bytes=len(payload),
        quarter_frames=int(np.sum(state.halves&1)),phase_mode=phase_mode,seed_gain_scale=seed_scale,guard_screen=guard_screen,source_sha256_normalized_lf=source_hashes,
        reference_sha256=reference_hash,seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        elapsed_seconds=time.perf_counter()-start,avr_implemented=False,hardware_tested=False,
        policy='Complete integer PC output; quarter flags explicitly tagged; serialized data excludes decoder, EOF and waves')
    base.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--evaluations',type=int,default=12000)
    p.add_argument('--phase-mode',type=int,choices=(0,1,2))
    a=p.parse_args();run(a.reference,a.model,a.output,a.evaluations,a.phase_mode)
