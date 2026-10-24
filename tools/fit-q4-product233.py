"""Train compact 2+3+3 spectral dictionaries through complete integer output.

Teacher coefficients initialize the dictionaries; the original PCM decides all
subsequent choices. Exact serialized size excludes the unimplemented decoder.
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
import q4_product233 as codec
from q4_voice_patterns import envelope_features
spec=importlib.util.spec_from_file_location('product233_lattice_api',ROOT/'tools/refine-q4-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


@dataclass
class State:
    pitches:np.ndarray
    local_gains:np.ndarray
    durations:np.ndarray
    indices:np.ndarray
    halves:np.ndarray
    root:np.ndarray
    middle:np.ndarray
    tail:np.ndarray
    waves_q1:np.ndarray

    def copy(self):return State(*(v.copy() for v in self.__dict__.values()))
    def fields(self):return {k:v.tolist() for k,v in self.__dict__.items()}


def expand(s):
    p,g,d,k,m,h=codec.expand(s.pitches,s.local_gains,s.durations,s.indices,s.halves,s.root,s.middle,s.tail)
    result=fit.State(p,g,d,k,m,s.waves_q1,h);fit.validate(result);return result


def medoids(distance,count=16):
    chosen=[int(np.argmin(distance.sum(axis=0)))];best=distance[:,chosen[0]].copy()
    while len(chosen)<count:
        scores=np.minimum(best[:,None],distance).sum(axis=0);scores[chosen]=np.inf
        index=int(np.argmin(scores));chosen.append(index);best=np.minimum(best,distance[:,index])
    for _ in range(15):
        labels=np.argmin(distance[:,chosen],axis=1);updated=[]
        for n,old in enumerate(chosen):
            members=np.flatnonzero(labels==n)
            updated.append(int(np.argmin(distance[members].sum(axis=0))) if len(members) else old)
        if updated==chosen:break
        chosen=updated
    labels=np.argmin(distance[:,chosen],axis=1).astype(np.int16)
    if np.any(distance[np.arange(len(labels)),np.asarray(chosen)[labels]]>=1e6):
        raise ValueError('Sixteen root records do not cover all waveform/gain windows')
    return np.asarray(chosen),labels


def initialize(teacher):
    p,g,d,k,m,b,h=(getattr(teacher,name) for name in fit.State.__annotations__)
    candidates=sorted(set((int(row[0]),int(row[1]),int(mode),base)
        for row,mode,gain in zip(k,m,g) for base,offset in enumerate(codec.OFFSETS) if offset<=gain<=offset+15))
    roots=np.asarray(candidates,np.int16);base=codec.OFFSETS[roots[:,3]]
    valid=((p[:,None]==0)|(g[:,None]==0)|(m[:,None]==roots[None,:,2]))
    valid&=(g[:,None]>=base[None,:])&(g[:,None]<=base[None,:]+15)
    distance=np.sum((k[:,None,:2].astype(float)-roots[None,:,:2])**2,axis=2)
    distance[~valid]=1e7;chosen,first=medoids(distance);root=roots[chosen]
    books=[];labels=[first]
    for group in (k[:,2:5],k[:,5:]):
        options=np.unique(group,axis=0)
        distance=np.sum((group[:,None,:].astype(float)-options[None,:,:])**2,axis=2)
        chosen,index=medoids(distance);books.append(options[chosen]);labels.append(index)
    local=g-codec.OFFSETS[root[first,3]]
    state=State(p.copy(),local.copy(),d.copy(),np.column_stack(labels),h.copy(),root,
        books[0].copy(),books[1].copy(),b.copy())
    # Jointly choose all three indices by the teacher's complete LPC response.
    # Independent coefficient distances can badly move narrow spectral peaks.
    grid=np.indices((16,16,16)).reshape(3,-1).T
    vectors=np.column_stack((state.root[grid[:,0],:2],state.middle[grid[:,1]],state.tail[grid[:,2]]))
    response=np.log(np.maximum(abs(np.fft.rfft(envelope_features(vectors),axis=1))[:,5:240],1e-5))
    wanted=np.log(np.maximum(abs(np.fft.rfft(envelope_features(k),axis=1))[:,5:240],1e-5))
    for row in range(len(p)):
        eligible=((p[row]==0)|(g[row]==0)|(state.root[:,2]==m[row]))
        eligible&=(g[row]>=codec.OFFSETS[state.root[:,3]])&(g[row]<=codec.OFFSETS[state.root[:,3]]+15)
        loss=np.mean((response-wanted[row])**2,axis=1);loss[~eligible[grid[:,0]]]=np.inf
        state.indices[row]=grid[int(np.argmin(loss))]
        state.local_gains[row]=g[row]-codec.OFFSETS[state.root[state.indices[row,0],3]]
    return state


def actions(s):
    for row in range(len(s.pitches)):
        for column in range(3):
            for label in range(16):
                if label!=s.indices[row,column]:yield ('index',row,column,label)
        for delta in (-1,1):yield ('gain',row,0,delta)
        if s.pitches[row]:
            for delta in (-2,-1,1,2):yield ('pitch',row,0,delta)
    for group,book in enumerate((s.root[:,:2],s.middle,s.tail)):
        for row in range(16):
            for column in range(book.shape[1]):
                for delta in (-1,1):yield ('coefficient',group,row,column,delta)
    for row in range(16):
        for delta in (-1,1):yield ('window',row,0,delta)
        for mode in range(8):
            if mode!=s.root[row,2]:yield ('mode',row,0,mode)
    for mode in range(8):
        for tap in range(16):
            for delta in (-1,1):yield ('wave',mode,tap,delta)
    for row in range(len(s.pitches)-1):
        for delta in (-64,64):yield ('boundary',row,0,delta)


def apply(s,action):
    kind=action[0];c=s.copy()
    if kind=='coefficient':
        _,group,row,column,delta=action;book=(c.root,c.middle,c.tail)[group]
        value=int(book[row,column])+delta
        if not -15<=value<=15:return None
        book[row,column]=value
    else:
        _,row,column,value=action
        if kind=='index':
            if column==0:
                gain=int(c.local_gains[row])+int(codec.OFFSETS[c.root[c.indices[row,0],3]])
                c.local_gains[row]=np.clip(gain-int(codec.OFFSETS[c.root[value,3]]),0,15)
            c.indices[row,column]=value
        elif kind=='gain':
            target=int(c.local_gains[row])+value
            if not 0<=target<=15:return None
            c.local_gains[row]=target
        elif kind=='pitch':
            target=int(c.pitches[row])*2+int(c.halves[row])+value
            if not 2<=target<=252:return None
            c.pitches[row]=target//2;c.halves[row]=target%2
        elif kind=='window':
            target=int(c.root[row,3])+value
            if not 0<=target<=7:return None
            c.root[row,3]=target
        elif kind=='mode':c.root[row,2]=value
        elif kind=='wave':
            target=int(c.waves_q1[row,column])+value
            if not -7<=target<=7:return None
            c.waves_q1[row,column]=target
        elif kind=='boundary':
            a=int(c.durations[row])+value;b=int(c.durations[row+1])-value
            if a not in (64,128,192,256) or b not in (64,128,192,256):return None
            c.durations[row]=a;c.durations[row+1]=b
        else:raise ValueError('Unknown product-dictionary action')
    try:expand(c)
    except ValueError:return None
    return c


def run(reference_path,teacher_path,output,evaluations=12000):
    if evaluations<0:raise ValueError('Expected nonnegative evaluation budget')
    start=time.perf_counter();meta=json.loads(teacher_path.read_text(encoding='utf-8'))
    if meta['schema']==codec.SCHEMA:s=State(*(np.asarray(meta[k],np.int16) for k in State.__annotations__))
    else:s=initialize(fit.load(teacher_path))
    bits,nearest=meta['state_bits'],meta['nearest'];x,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or x.ndim!=1 or len(x)!=int(s.durations.sum()):raise ValueError('Expected complete mono7500 original')
    reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if reference_hash!=meta['reference_sha256']:raise ValueError('Teacher original hash mismatch')
    source_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
        for p in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q4_product233.py',ROOT/'tools/refine-q4-lattice.py',ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py')}
    spectral=fit.SpectrogramObjective(x);history=[];epochs=[];evaluated=0
    def score(state,detail=False):
        pcm,counts=fit.render(expand(state),bits,nearest);raw=pcm.astype(np.int16)-128;y=raw.astype(float)/128
        q=dict(stoi=float(fit.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),wrap_counts=counts.tolist(),
            guards_pass=bool(not np.any(counts) and abs(raw).max()<=115 and not np.any(abs(np.diff(raw))>=48)),
            pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
        if detail:q.update(estoi=fit.deterministic_estoi(x,y,7500),harmonic_metrics=fit.HarmonicTrackObjective(x).evaluate(y))
        return q
    def energy(q):return fit.energy(q)+1000*sum(q['wrap_counts'])+10*max(0,q['peak']-115)+10*max(0,q['maximum_step']-47)
    def export(state):return dict(schema=codec.SCHEMA,sample_rate=7500,state_bits=bits,nearest=nearest,
        **state.fields(),reference_sha256=reference_hash,avr_implemented=False,hardware_tested=False)
    output.mkdir(parents=True,exist_ok=True);initial=current=score(s,True);fit.save(output/'initial-model.json',export(s))
    print(json.dumps(dict(evaluated=0,score=initial)),flush=True)
    epoch=0
    while evaluated<evaluations:
        accepted=0;proposals=list(actions(s))
        if epoch%2:proposals.reverse()
        for action in proposals:
            if evaluated>=evaluations:break
            candidate=apply(s,action)
            if candidate is None:continue
            evaluated+=1;q=score(candidate)
            if energy(q)<energy(current)-1e-12:
                s,current=candidate,q;accepted+=1;history.append(dict(evaluation=evaluated,action=list(action),score=q))
            if evaluated%250==0:
                fit.save(output/'checkpoint.json',export(s));fit.save(output/'progress.json',dict(evaluated=evaluated,accepted=len(history),score=current,elapsed_seconds=time.perf_counter()-start))
                print(json.dumps(dict(evaluated=evaluated,accepted=len(history),stoi=current['stoi'],spectrum=current['spectrogram_loss'],guards_pass=current['guards_pass'])),flush=True)
        epochs.append(dict(epoch=epoch,evaluated=evaluated,accepted=accepted));epoch+=1
        if not accepted:break
    table=codec.pack_tables(s.root,s.middle,s.tail);payload=codec.pack_frames(s.pitches,s.local_gains,s.durations,s.indices,s.halves)
    for expected,got in zip((s.root,s.middle,s.tail),codec.unpack_tables(table)):np.testing.assert_array_equal(expected,got)
    for expected,got in zip((s.pitches,s.local_gains,s.durations,s.indices,s.halves),codec.unpack_frames(payload)):np.testing.assert_array_equal(expected,got)
    final=score(s,True);fit.save(output/'model.json',export(s))
    pcm,_=fit.render(expand(s),bits,nearest);sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report=dict(schema='q4-product233-study-v1',initial=initial,final=final,evaluated=evaluated,accepted=len(history),history=history,epochs=epochs,
        table_bytes=len(table),stream_bytes=len(payload),data_bytes=len(table)+len(payload),
        source_sha256_normalized_lf=source_hashes,reference_sha256=reference_hash,
        seed_sha256=hashlib.sha256(teacher_path.read_bytes()).hexdigest(),elapsed_seconds=time.perf_counter()-start,
        avr_implemented=False,hardware_tested=False,policy='Exact packed PC format; no total decoder-size or timing claim; invalid guard endpoints are not playable candidates')
    fit.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','teacher','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--evaluations',type=int,default=12000)
    a=p.parse_args();run(a.reference,a.teacher,a.output,a.evaluations)
