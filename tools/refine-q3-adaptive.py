"""Full-clip coordinate fitting with measured memory and harmonic guardrails.

Keep the starting STOI/eSTOI, spectral loss, DC and strong-component errors.
No audio blocks are synthesized independently, aligned, normalized or spliced.
"""
import argparse
from collections import Counter
import importlib.util
from itertools import zip_longest
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('adaptive_polish_eight',ROOT/'tools/probe-q3-pulsebook8.py')
probe=importlib.util.module_from_spec(spec);sys.modules[spec.name]=probe;spec.loader.exec_module(probe)
from q3_adaptive import select


class Objective(probe.search.Objective):
    def __init__(self,reference):
        super().__init__(reference,floor_budget=1024,rounded_budget=1024)
        self.tracks=probe.HarmonicTrackObjective(reference)
        self.limits=None;self.rejected=Counter()

    def evaluate(self,state):
        layout=select(state.frames,state.durations,state.book)
        if layout['flash_bytes']>1024:
            self.rejected['complete_flash']+=1;return None
        state.frames,state.book=layout['frames'],layout['book']
        self.floor_budget=layout['maximum_stream_bytes']
        score=super().evaluate(state)
        if score is None:return None
        if self.limits is not None:
            for key in ('stoi','spectrogram_loss','raw_mean'):
                worse=(score[key]<self.limits[key] if key=='stoi' else
                    abs(score[key])>abs(self.limits[key]) if key=='raw_mean' else score[key]>self.limits[key])
                if worse:self.rejected[key]+=1;return None
        pcm,_=probe.codec.render(state.frames,state.durations,state.book)
        audio=(pcm.astype(float)-128)/128
        score['estoi']=probe.deterministic_estoi(self.reference,audio,7500)
        if self.limits is not None and score['estoi']<self.limits['estoi']:
            self.rejected['estoi']+=1;return None
        detail=self.tracks.details(audio);score['harmonic_metrics']=detail['metrics']
        score['partial_violation_power']=probe.check_partial_bounds(detail,duration_seconds=len(audio)/7500)['violating_reference_power_fraction']
        if self.limits is not None:
            for key in ('frequency_error_cents','frequency_trajectory_error','level_error_db',
                    'harmonic_track_loss','missing_reference_energy'):
                if score['harmonic_metrics'][key]>self.limits['harmonic_metrics'][key]:
                    self.rejected[key]+=1;return None
            if score['partial_violation_power']>self.limits['partial_violation_power']:
                self.rejected['partial_violation_power']+=1;return None
        score.update(flash_bytes=layout['flash_bytes'],code_bytes=layout['code_bytes'],
            active_forms=layout['active_forms'],stored_forms=layout['stored_forms'],
            waveform_bytes=layout['book_bytes'],speech_prefix_bytes=layout['prefix_bytes'],
            maximum_stream_bytes=layout['maximum_stream_bytes'])
        return score

    def energy(self,score):
        h=score['harmonic_metrics']
        return (super().energy(score)+.1*h['harmonic_track_loss']+
            .0005*h['frequency_error_cents']+.005*h['level_error_db']+.1*abs(score['raw_mean']))


def actions(state):
    n=len(state.frames)
    groups=[
        [('tap',row,col,delta) for row in range(8) for col in range(4) for delta in (-1,1)],
        [('tap_pair',row,col,delta) for row in range(8) for col in range(4) for delta in (-1,1)],
        [('pitch',i,0,delta) for i in range(n) for delta in (-2,-1,1,2)],
        [('gain',i,0,delta) for i in range(n) for delta in (-1,1)],
        [('mode',i,mode,delta) for i in range(n) for mode in range(8) for delta in (0,-1,1)],
        [('coefficient_run',i,k,delta) for i in range(n) for k in range(8) for delta in (-1,1)],
        [('coefficient_frame',i,k,delta) for i in range(n) for k in range(8) for delta in (-1,1)],
        [('boundary',i,0,delta) for i in range(n-1) for delta in (-64,64)],
        [('pitch_block',i,0,delta) for i in range(n-1) for delta in (-1,1)]]
    return [a for row in zip_longest(*groups) for a in row if a is not None]


def apply(state,action):
    kind,index,position,delta=action
    f,d,b=state.frames.copy(),state.durations.copy(),state.book.copy()
    if kind.startswith('tap'):
        target=int(b[index,position])+delta
        if not -7<=target<=7:return None
        b[index,position]=target
        if kind=='tap_pair':
            other=(position+1)%4;target=int(b[index,other])-delta
            if not -7<=target<=7:return None
            b[index,other]=target
    elif kind in ('pitch','pitch_block'):
        end=min(len(f),index+(3 if kind=='pitch_block' else 1))
        for i in range(index,end):
            target=int(f[i,0])+delta
            if not f[i,0] or not 1<=target<=126:return None
            f[i,0]=target
    elif kind in ('gain','mode'):
        gain=(int(f[index,1])&15)+delta
        if not 0<=gain<=15:return None
        mode=(int(f[index,1])>>4) if kind=='gain' else position
        f[index,1]=(mode<<4)|gain
    elif kind.startswith('coefficient'):
        column,shift=2+position//2,(position%2)*4
        target=((int(f[index,column])>>shift)&15)+delta
        if not 1<=target<=15:return None
        first,last=index,index+1
        if kind=='coefficient_run':
            half=2 if column<4 else 4;old=f[index,half:half+2].copy()
            while first and np.array_equal(f[first-1,half:half+2],old):first-=1
            while last<len(f) and np.array_equal(f[last,half:half+2],old):last+=1
        f[first:last,column]=(f[first:last,column]&(255^(15<<shift)))|(target<<shift)
    elif kind=='boundary':
        if not 64<=int(d[index])+delta<=256 or not 64<=int(d[index+1])-delta<=256:return None
        d[index],d[index+1]=int(d[index])+delta,int(d[index+1])-delta
    else:raise ValueError('Unknown coordinate')
    layout=select(f,d,b)
    return probe.search.State(layout['frames'],d,layout['book'],False,1)


def key(state):return state.frames.tobytes(),state.durations.tobytes(),state.book.tobytes()


def run(reference_path,model_path,output,*,evaluations=5000,passes=2):
    if evaluations<1 or passes<1:raise ValueError('Expected bounded positive search budget')
    started=time.perf_counter();reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected complete mono7500 reference')
    f,d,b,_=probe.builder.load_model(model_path)
    objective=Objective(reference);current=probe.search.State(f,d,b,False,1)
    current.score=objective.evaluate(current)
    if current.score is None:raise ValueError('Starting model fails guards')
    objective.limits=current.score;initial=current
    before=probe.export(output/'before',initial,objective,4,probe.sha(reference_path))
    seen={key(current)};valid=exact=accepted=0;history=[];classes=Counter()
    for epoch in range(passes):
        sequence=actions(current)
        if epoch%2:sequence.reverse()
        for action in sequence:
            if exact>=evaluations:break
            trial=apply(current,action)
            if trial is None or key(trial) in seen:continue
            seen.add(key(trial));exact+=1;classes[action[0]]+=1
            trial.score=objective.evaluate(trial)
            if trial.score is not None:
                valid+=1
                if objective.energy(trial.score)<objective.energy(current.score)-1e-12:
                    current=trial;accepted+=1
                    history.append(dict(evaluation=exact,action=list(action),score=current.score))
            if exact%250==0:
                progress=dict(evaluated=exact,accepted=accepted,valid=valid,score=current.score,
                    elapsed_seconds=time.perf_counter()-started)
                probe.save(output/'progress.json',progress);print(probe.json.dumps(progress),flush=True)
        if exact>=evaluations:break
    objective.floor_budget=current.score['maximum_stream_bytes']
    after=probe.export(output/'after',current,objective,4,probe.sha(reference_path))
    report=dict(schema='q3-adaptive-refine-v1',before=before,after=after,evaluated=exact,accepted=accepted,
        valid=valid,requested_evaluations=evaluations,passes=passes,history=history,
        evaluated_classes=dict(classes),quality_rejections=dict(objective.rejected),arithmetic_rejections=objective.invalid,
        input_model_sha256=probe.sha(model_path),reference_sha256=probe.sha(reference_path),
        elapsed_seconds=time.perf_counter()-started,
        policy='No starting STOI/eSTOI, spectrum, absolute DC, strong-component frequency/trajectory/level/loss/missing-energy or strict 5dB power regression; exact full-clip synthesis, measured complete-image packing; no target relaxation',
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():probe.hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
            for p in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q3_adaptive.py',ROOT/'tools/probe-q3-pulsebook8.py',ROOT/'tools/probe-q3-pulsebook.py')})
    probe.save(output/'report.json',report)
    print(probe.json.dumps(dict(evaluated=exact,accepted=accepted,stoi=after['stoi'],estoi=after['estoi'],spectrum=after['spectrogram_loss'])),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','model','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--evaluations',type=int,default=5000);p.add_argument('--passes',type=int,default=2)
    a=p.parse_args();run(a.reference,a.model,a.output,evaluations=a.evaluations,passes=a.passes)
