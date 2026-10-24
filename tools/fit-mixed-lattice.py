"""Find a higher-quality integer teacher with selectable reflection precision.

Q5/Q7 low stages address the sensitivity of low voice resonances. Zero-area pulse
shapes are optional and fitted with paired tap moves. This is PC research, not
a complete ATtiny13 decoder, memory fit or timing qualification.
"""
import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import mixed_lattice as codec
import q4_phase_wave as phase
spec=importlib.util.spec_from_file_location('mixed_fit_metrics',ROOT/'tools/refine-q4-lattice.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)


@dataclass
class State:
    pitches:np.ndarray
    gains_q1:np.ndarray
    durations:np.ndarray
    coefficients:np.ndarray
    modes:np.ndarray
    waves_q1:np.ndarray
    quarters:np.ndarray
    phase_modes:np.ndarray|None=None
    wave_fraction_bits:int=1
    tail_policy:str='literal'

    def copy(self):return State(*(a.copy() if isinstance(a,np.ndarray) else a for a in self.__dict__.values()))
    def fields(self):
        result={k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in self.__dict__.items()
            if v is not None and k not in ('waves_q1','tail_policy')}
        key='wave_heads' if self.tail_policy=='balance16' else 'wave_taps' if self.wave_fraction_bits!=1 else 'waves_q1'
        result[key]=(self.waves_q1[:,:16] if self.tail_policy=='balance16' else self.waves_q1).tolist()
        if self.tail_policy!='literal':result['tail_policy']=self.tail_policy
        return result


def zero_area(waves,limit=7):
    """Nearest bounded integer projection, preserving attack on equal costs."""
    original=np.asarray(waves,np.int16);result=original.copy()
    for row in range(len(result)):
        while int(result[row].sum()):
            delta=-1 if result[row].sum()>0 else 1
            choices=[i for i in range(result.shape[1]-1,-1,-1) if -limit<=int(result[row,i])+delta<=limit]
            tap=min(choices,key=lambda i:(int(result[row,i])+delta-int(original[row,i]))**2-(int(result[row,i])-int(original[row,i]))**2)
            result[row,tap]+=delta
    return result


def step_bound(reference,policy):
    if policy not in ('legacy','reference'):raise ValueError('Unknown step policy')
    return 47 if policy=='legacy' else max(1,min(255,int(np.ceil(np.max(abs(np.diff(np.asarray(reference)*128)))))))


def load(path,order=None,profile=None,state_bits=None,zero_mean=False,pulse_length=None,fit_phase=False,wave_fraction_bits=None,tail_policy=None):
    m=json.loads(path.read_text(encoding='utf-8'));schema=m['schema']
    if schema not in ('q4-lattice-fit-v1','q4-quarter-fit-v1',codec.SCHEMA,codec.PULSE_SCHEMA,codec.BALANCED_SCHEMA):raise ValueError('Expected a tagged lattice teacher')
    raw={name:np.asarray(m['wave_taps' if name=='waves_q1' and m.get('wave_fraction_bits',1)!=1 else name if name!='quarters' else 'halves' if schema=='q4-lattice-fit-v1' else 'quarters'],np.int16)
        for name in State.__annotations__ if name not in ('phase_modes','wave_fraction_bits','tail_policy','waves_q1')}
    old_tail=m.get('tail_policy','literal')
    if (old_tail=='balance16')!=(schema==codec.BALANCED_SCHEMA):raise ValueError('Tail policy does not match its schema')
    tail_policy=old_tail if tail_policy is None else tail_policy
    if tail_policy not in ('literal','balance16'):raise ValueError('Unknown tail policy')
    raw['tail_policy']=tail_policy
    raw['waves_q1']=np.asarray(m['wave_heads' if old_tail=='balance16' else 'wave_taps' if m.get('wave_fraction_bits',1)!=1 else 'waves_q1'],np.int16)
    old_wave_bits=m.get('wave_fraction_bits',1)
    if old_wave_bits not in (1,2) or (old_wave_bits!=1 and schema not in (codec.PULSE_SCHEMA,codec.BALANCED_SCHEMA)):raise ValueError('Wave precision does not match its schema')
    wave_fraction_bits=old_wave_bits if wave_fraction_bits is None else wave_fraction_bits
    if wave_fraction_bits not in (1,2):raise ValueError('Expected one or two wave fraction bits')
    if wave_fraction_bits<old_wave_bits and np.any(raw['waves_q1']%2):raise ValueError('Cannot silently discard wave precision')
    raw['waves_q1']=(raw['waves_q1']*2 if wave_fraction_bits>old_wave_bits else raw['waves_q1']//2 if wave_fraction_bits<old_wave_bits else raw['waves_q1'])
    raw['wave_fraction_bits']=wave_fraction_bits
    if old_tail=='balance16':raw['waves_q1']=codec.balanced_pulses(raw['waves_q1'],wave_fraction_bits)
    if 'phase_modes' in m and schema not in (codec.PULSE_SCHEMA,codec.BALANCED_SCHEMA):raise ValueError('Per-frame phase controls require the pulse schema')
    raw['phase_modes']=np.asarray(m['phase_modes'],np.int16) if 'phase_modes' in m else (
        np.full(len(raw['pitches']),m.get('phase_mode',0),np.int16) if fit_phase else None)
    if schema=='q4-lattice-fit-v1':raw['quarters']*=2
    old_width=raw['waves_q1'].shape[1]
    if old_width!=(m.get('pulse_length') if schema in (codec.PULSE_SCHEMA,codec.BALANCED_SCHEMA) else 16):raise ValueError('Pulse width does not match its schema')
    pulse_length=(32 if tail_policy=='balance16' else old_width) if pulse_length is None else pulse_length
    if tail_policy=='balance16' and pulse_length!=32:raise ValueError('Balanced tails require 32 logical taps')
    if pulse_length not in (16,32):raise ValueError('Expected 16 or 32 pulse taps')
    if pulse_length<old_width and np.any(raw['waves_q1'][:,pulse_length:]):raise ValueError('Cannot silently truncate nonzero pulse tails')
    raw['waves_q1']=np.pad(raw['waves_q1'][:,:pulse_length],((0,0),(0,max(0,pulse_length-old_width))))
    old_bits=np.asarray(m.get('coefficient_bits',[4]*raw['coefficients'].shape[1]),np.int16)
    order=raw['coefficients'].shape[1] if order is None else order
    if order not in (6,8,10):raise ValueError('Expected 6, 8 or 10 stages')
    preserve_bits=profile is None and schema in (codec.SCHEMA,codec.PULSE_SCHEMA,codec.BALANCED_SCHEMA)
    if profile is None:profile=m.get('precision_profile','head7')
    bits=np.full(order,7 if profile=='all7' else 4,np.int16)
    if profile=='head7':bits[:2]=7
    if profile=='head5':bits[:2]=5
    if preserve_bits:bits[:min(order,len(old_bits))]=old_bits[:min(order,len(old_bits))]
    coefficients=np.zeros((len(raw['pitches']),order),np.int16)
    for j in range(min(order,len(old_bits))):
        limit=(1<<int(bits[j]))-1
        coefficients[:,j]=np.clip(np.rint(raw['coefficients'][:,j].astype(float)*2.**(int(bits[j])-int(old_bits[j]))),-limit,limit)
    raw['coefficients']=coefficients;zero_mean=zero_mean or m.get('zero_mean',False)
    if tail_policy=='balance16':
        raw['waves_q1']=codec.balanced_pulses(raw['waves_q1'][:,:16],wave_fraction_bits);zero_mean=True
    elif zero_mean:raw['waves_q1']=zero_area(raw['waves_q1'],7<<(wave_fraction_bits-1))
    state=State(**raw);state_bits=m.get('state_bits',6) if state_bits is None else state_bits
    validate(state,bits,state_bits,zero_mean)
    return state,bits,state_bits,m.get('phase_mode',0),profile,zero_mean,m


def validate(s,bits,state_bits,zero_mean=False):
    codec.validate(s.coefficients,bits,state_bits);n=len(s.pitches)
    if s.wave_fraction_bits not in (1,2):raise ValueError('Invalid pulse precision')
    if s.tail_policy not in ('literal','balance16'):raise ValueError('Invalid tail policy')
    if s.tail_policy=='balance16' and not np.array_equal(s.waves_q1,codec.balanced_pulses(s.waves_q1[:,:16],s.wave_fraction_bits)):
        raise ValueError('Balanced pulse tails must agree with their heads')
    limit=7<<(s.wave_fraction_bits-1)
    if (not n or s.pitches.shape!=(n,) or any(a.shape!=(n,) for a in (s.gains_q1,s.durations,s.modes,s.quarters))
            or s.coefficients.shape[0]!=n or s.waves_q1.shape not in ((8,16),(8,32))
            or any(a.dtype.kind not in 'iu' for a in s.__dict__.values() if isinstance(a,np.ndarray))
            or np.any(s.pitches<0) or np.any(s.pitches>126) or np.any(s.gains_q1<0) or np.any(s.gains_q1>30)
            or np.any(s.modes<0) or np.any(s.modes>7) or np.any(s.waves_q1 < -limit) or np.any(s.waves_q1>limit)
            or np.any(s.quarters<0) or np.any(s.quarters>3) or np.any((s.pitches==0)&(s.quarters!=0))
            or not np.all(np.isin(s.durations,[64,128,192,256]))
            or (zero_mean and np.any(s.waves_q1.sum(axis=1)))
            or (s.phase_modes is not None and (s.phase_modes.shape!=(n,) or np.any(s.phase_modes<0) or np.any(s.phase_modes>3)))):raise ValueError('Invalid mixed-lattice controls')


def render(s,bits,state_bits,phase_mode):
    rows,excitation=phase.legacy_excitation(s.pitches,s.gains_q1,s.durations,s.modes,s.waves_q1,s.quarters,pitch_bits=2,phase_mode=phase_mode,phase_modes=s.phase_modes,pulse_width=s.waves_q1.shape[1])
    excitation[s.pitches[rows]==0]*=1<<s.wave_fraction_bits
    return codec.filter_signal(excitation,rows,s.coefficients,bits,state_bits=state_bits,nearest=True,fraction_bits=s.wave_fraction_bits+1)


def source_pitch_hints(reference,durations):
    from period_wave import track_pitch
    centers,f0,_=track_pitch(reference)
    midpoints=np.cumsum(durations)-np.asarray(durations)/2
    return np.asarray([int(np.clip(round(4*7500/f0[i]),4,507)) if f0[i]>0 else 0
        for i in (int(np.argmin(abs(centers-t))) for t in midpoints)],np.int16)


def actions(s,bits,zero_mean,pitch_hints=None):
    for row in range(len(s.pitches)):
        if pitch_hints is not None:
            current=int(s.pitches[row])*4+int(s.quarters[row]);periods={0,current}
            for target in (current,int(pitch_hints[row])):
                if target:
                    periods.update((target,round(target/2),target*2))
            for neighbor in (row-1,row+1):
                if 0<=neighbor<len(s.pitches) and s.pitches[neighbor]:
                    periods.add(int(s.pitches[neighbor])*4+int(s.quarters[neighbor]))
            gains=sorted(set(max(1,min(30,round(int(s.gains_q1[row])*scale))) for scale in (.5,.75,1.,1.5,2.)))
            modes=np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)])
            for period in sorted(p for p in periods if p==0 or 4<=p<=507):
                if period==current:continue
                for gain in gains:
                    for mode in (modes if period and not current else [s.modes[row]]):
                        for phase in ((0,3) if period and not current else [int(s.phase_modes[row]) if s.phase_modes is not None else 0]):
                            yield ('voice',row,period,gain,int(mode),phase)
        if s.phase_modes is not None and s.pitches[row]:
            for mode in range(4):
                if mode!=s.phase_modes[row]:yield ('phase',row,0,mode)
        for column in range(s.coefficients.shape[1]):
            for delta in ((-8,-4,-2,-1,1,2,4,8) if bits[column]>4 else (-1,1)):
                yield ('coefficient',row,column,delta)
        for delta in (-1,1):yield ('gain',row,0,delta)
        if s.pitches[row]:
            for delta in (-2,-1,1,2):yield ('pitch',row,0,delta)
        for mode in np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)]):
            if mode!=s.modes[row]:yield ('mode',row,0,int(mode))
    for mode in np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)]):
        for first in range(16 if s.tail_policy=='balance16' else s.waves_q1.shape[1]):
            for second in (range(first+1,s.waves_q1.shape[1]) if zero_mean and s.tail_policy=='literal' else [-1]):
                for delta in (-1,1):yield ('wave',int(mode),first,delta,second)
    for row in range(len(s.pitches)-1):
        for delta in (-64,64):yield ('boundary',row,0,delta)


def apply(s,action,bits):
    c=s.copy();kind,row,column,value=action[:4]
    if kind=='voice':
        if (column!=0 and not 4<=column<=507) or not 0<=value<=30:return None
        c.pitches[row]=column//4;c.quarters[row]=column%4;c.gains_q1[row]=value;c.modes[row]=action[4]
        if c.phase_modes is not None:c.phase_modes[row]=action[5]
    elif kind=='coefficient':
        target=int(c.coefficients[row,column])+value;limit=(1<<int(bits[column]))-1
        if not -limit<=target<=limit:return None
        c.coefficients[row,column]=target
    elif kind=='gain':
        target=int(c.gains_q1[row])+value
        if not 0<=target<=30:return None
        c.gains_q1[row]=target
    elif kind=='pitch':
        target=int(c.pitches[row])*4+int(c.quarters[row])+value
        if not 4<=target<=507:return None
        c.pitches[row]=target//4;c.quarters[row]=target%4
    elif kind=='mode':c.modes[row]=value
    elif kind=='phase':
        if c.phase_modes is None or not 0<=value<=3:return None
        c.phase_modes[row]=value
    elif kind=='wave':
        limit=7<<(c.wave_fraction_bits-1)
        second=action[4];target=int(c.waves_q1[row,column])+value
        if not -limit<=target<=limit or (second>=0 and not -limit<=int(c.waves_q1[row,second])-value<=limit):return None
        c.waves_q1[row,column]=target
        if second>=0:c.waves_q1[row,second]-=value
        if c.tail_policy=='balance16':c.waves_q1=codec.balanced_pulses(c.waves_q1[:,:16],c.wave_fraction_bits)
    elif kind=='boundary':
        a=int(c.durations[row])+value;b=int(c.durations[row+1])-value
        if a not in (64,128,192,256) or b not in (64,128,192,256):return None
        c.durations[row]=a;c.durations[row+1]=b
    else:raise ValueError('Unknown mixed-lattice action')
    return c


def run(reference_path,model_path,output,evaluations=24000,order=None,profile=None,state_bits=None,zero_mean=False,pulse_length=None,wave_first=False,fit_phase=False,wave_fraction_bits=None,step_policy=None,voice_search=False,tail_policy=None):
    if evaluations<0:raise ValueError('Expected nonnegative evaluation budget')
    start=time.perf_counter();s,bits,state_bits,phase_mode,profile,zero_mean,meta=load(model_path,order,profile,state_bits,zero_mean,pulse_length,fit_phase or voice_search,wave_fraction_bits,tail_policy)
    x,sr=sf.read(reference_path,dtype='float64');reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if sr!=7500 or x.ndim!=1 or len(x)!=int(s.durations.sum()) or reference_hash!=meta['reference_sha256']:
        raise ValueError('Expected unchanged complete mono7500 original')
    step_policy=meta.get('step_policy','legacy') if step_policy is None else step_policy
    step_limit=step_bound(x,step_policy)
    source_paths=[Path(__file__),ROOT/'ATtiny13A/Sound/codec/mixed_lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py']
    if voice_search:source_paths.append(ROOT/'ATtiny13A/Sound/codec/period_wave.py')
    source_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in source_paths}
    pitch_hints=source_pitch_hints(x,s.durations) if voice_search else None
    spectral=base.SpectrogramObjective(x);history=[];epochs=[];evaluated=0
    def score(state,detail=False):
        pcm,counts=render(state,bits,state_bits,phase_mode);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>step_limit):return None
        y=raw.astype(float)/128;q=dict(stoi=float(base.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            raw_rms=float(np.sqrt(np.mean(y*y))),peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),
            wrap_counts=counts.tolist(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
        if detail:q.update(estoi=base.deterministic_estoi(x,y,7500),harmonic_metrics=base.HarmonicTrackObjective(x).evaluate(y))
        return q
    initial=current=score(s,True);seed_scale=1.
    if initial is None:
        old_g=s.gains_q1.copy()
        for scale in (.875,.75,.625,.5):
            s.gains_q1=np.where(old_g>0,np.maximum(1,np.floor(old_g*scale)),0).astype(np.int16)
            initial=current=score(s,True)
            if initial is not None:seed_scale=scale;break
    if initial is None:raise ValueError('No integer-guarded initial seed')
    def export(state):return dict(schema=codec.BALANCED_SCHEMA if state.tail_policy=='balance16' else codec.SCHEMA if state.waves_q1.shape[1]==16 and state.phase_modes is None and state.wave_fraction_bits==1 else codec.PULSE_SCHEMA,
        **({} if state.waves_q1.shape[1]==16 and state.phase_modes is None and state.wave_fraction_bits==1 else dict(pulse_length=int(state.waves_q1.shape[1]))),
        sample_rate=7500,coefficient_bits=bits.tolist(),state_bits=state_bits,nearest=True,
        precision_profile=profile,zero_mean=zero_mean,phase_mode=phase_mode,**state.fields(),reference_sha256=reference_hash,
        step_policy=step_policy,step_limit=step_limit,
        avr_implemented=False,serialized_format=False,hardware_tested=False)
    output.mkdir(parents=True,exist_ok=True);base.save(output/'initial-model.json',export(s))
    print(json.dumps(dict(evaluated=0,order=len(bits),profile=profile,state_bits=state_bits,zero_mean=zero_mean,score=initial)),flush=True)
    best=(initial['stoi'],s.copy(),initial);epoch=0
    while evaluated<evaluations:
        accepted=0;proposals=list(actions(s,bits,zero_mean,pitch_hints))
        if epoch%2:proposals.reverse()
        if wave_first:proposals.sort(key=lambda action:action[0]!='wave')
        for action in proposals:
            if evaluated>=evaluations:break
            candidate=apply(s,action,bits)
            if candidate is None:continue
            evaluated+=1;q=score(candidate)
            if q is not None and base.energy(q)<base.energy(current)-1e-12:
                s,current=candidate,q;accepted+=1
                history.append(dict(evaluation=evaluated,action=list(action),stoi=q['stoi'],spectrogram_loss=q['spectrogram_loss'],pcm_sha256=q['pcm_sha256']))
                if q['stoi']>best[0] and q['spectrogram_loss']<=.4848481735668308 and abs(q['raw_mean'])<=.07764022651760058:best=(q['stoi'],s.copy(),q)
            if evaluated%250==0:
                progress=dict(evaluated=evaluated,accepted=len(history),score=current,elapsed_seconds=time.perf_counter()-start)
                base.save(output/'progress.json',progress);base.save(output/'checkpoint.json',export(s));print(json.dumps(progress),flush=True)
        epochs.append(dict(epoch=epoch,evaluated=evaluated,accepted=accepted));epoch+=1
        if not accepted:break
    final=score(s,True);best_detail=score(best[1],True)
    validate(s,bits,state_bits,zero_mean);base.save(output/'model.json',export(s));base.save(output/'best-intelligibility-model.json',export(best[1]))
    pcm,_=render(s,bits,state_bits,phase_mode);sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report=dict(schema='mixed-lattice-study-v1',initial=initial,final=final,best_intelligibility=best_detail,
        evaluated=evaluated,accepted=len(history),history=history,epochs=epochs,order=len(bits),state_bits=state_bits,
        coefficient_bits=bits.tolist(),zero_mean=zero_mean,seed_gain_scale=seed_scale,
        pulse_length=int(s.waves_q1.shape[1]),wave_first=wave_first,fit_phase=s.phase_modes is not None,wave_fraction_bits=s.wave_fraction_bits,
        tail_policy=s.tail_policy,
        step_policy=step_policy,step_limit=step_limit,reference_maximum_step=float(np.max(abs(np.diff(x*128)))),
        voice_search=voice_search,source_pitch_hints=pitch_hints.tolist() if pitch_hints is not None else None,
        reference_sha256=reference_hash,seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        source_sha256_normalized_lf=source_hashes,elapsed_seconds=time.perf_counter()-start,
        avr_implemented=False,serialized_format=False,hardware_tested=False,policy='PC quality teacher; no memory-fit or sample-deadline claim')
    base.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--evaluations',type=int,default=24000);p.add_argument('--order',type=int,choices=(6,8,10))
    p.add_argument('--profile',choices=('q4','head5','head7','all7'));p.add_argument('--state-bits',type=int,choices=(0,4,6,8))
    p.add_argument('--zero-mean',action='store_true');p.add_argument('--pulse-length',type=int,choices=(16,32))
    p.add_argument('--wave-first',action='store_true')
    p.add_argument('--fit-phase',action='store_true')
    p.add_argument('--wave-fraction-bits',type=int,choices=(1,2));p.add_argument('--step-policy',choices=('legacy','reference'))
    p.add_argument('--voice-search',action='store_true');p.add_argument('--tail-policy',choices=('literal','balance16'));a=p.parse_args()
    run(a.reference,a.model,a.output,a.evaluations,a.order,a.profile,a.state_bits,a.zero_mean,a.pulse_length,a.wave_first,a.fit_phase,a.wave_fraction_bits,a.step_policy,a.voice_search,a.tail_policy)
