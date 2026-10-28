"""Exact v5 byte accounting and bounded marginal optional-pulse reclamation.

Rendering and distortion belong to callers. This module never imports a search
or objective implementation, so each path can bind its own exact state/model.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral, Real

import numpy as np
from lpx4 import BitWriter
import speech_compact as compact


def spectrum_bits(vector, previous, profile):
    """Compatibility cost of the serializer's actual gap/delta/repeat choice."""
    writer=BitWriter()
    compact.put_spectrum(writer,list(map(int,vector)),
                         None if previous is None else list(map(int,previous)),
                         5 if profile==4 else 6)
    return writer.total


def _base_bits(spectra_bits,frames,profile):
    return spectra_bits+frames*(110 if profile==4 else 166)


def extra_capacity(spectra_bits,frames,profile,max_bytes,slots=None):
    """Maximum active extras with their mandatory per-chunk marker overhead.

    Zero capacity does not establish feasibility: fixed fields can exceed the
    cap, or fit only when the extras flag and all its marker bits disappear.
    """
    if slots is None:slots=frames*8
    return max(0,min(slots,((max_bytes-22)*8-_base_bits(spectra_bits,frames,profile)-frames*8)//10))


def _layout(spectral,frames,profile,active,force_extras=False):
    enhanced=bool(force_extras or active)
    params=frames*30;base_pulses=frames*(80 if profile==4 else 136)
    markers=frames*8 if enhanced else 0;values=active*10
    bits=spectral+params+base_pulses+markers+values;padding=(-bits)%8
    return {'frames':frames,'header_bytes':22,'spectrum_bits':spectral,
            'parameter_bits':params,'base_pulse_bits':base_pulses,
            'extra_marker_bits':markers,'extra_value_bits':values,'extra_pulses':active,
            'payload_bits':bits,'padding_bits':padding,'file_bytes':22+(bits+padding)//8}


def bit_accounting(spectra,profile,extras=None,*,force_extras=False):
    """Count complete stored frames, headers, extras markers and byte padding.

    Sample tails do not shorten their last 320-sample stored packet. Parameter
    values do not affect v5's fixed-width scale/lag/gain/base-pulse cost.
    """
    if profile not in (4,6):raise ValueError('Expected v5 profile4 or6')
    vectors=np.asarray(spectra)
    if vectors.ndim!=2 or vectors.shape[1]!=10 or not 1<=len(vectors)<=200 or vectors.dtype.kind not in 'iu':
        raise ValueError('Expected one to200 complete ten-value spectra')
    if np.any(vectors<0) or np.any(vectors>=(32 if profile==4 else 64)) or np.any(np.diff(vectors.astype(np.int64),axis=1)<=0):
        raise ValueError('Expected ordered legal v5 spectra')
    frames=len(vectors);slots=frames*8
    if extras is None:added=np.zeros((slots,2),np.int64)
    else:
        added=np.asarray(extras)
        if added.shape!=(slots,2) or added.dtype.kind not in 'iu':raise ValueError('Invalid v5 extras geometry')
        if np.any(added[:,1]<-8) or np.any(added[:,1]>7):raise ValueError('Invalid v5 extra amplitude')
        active_mask=added[:,1]!=0
        if np.any(added[active_mask,0]<0) or np.any(added[active_mask,0]>=40):raise ValueError('Invalid v5 extra position')
    active=int(np.count_nonzero(added[:,1]))
    spectral=sum(spectrum_bits(row,None if i==0 else vectors[i-1],profile) for i,row in enumerate(vectors))
    return _layout(spectral,frames,profile,active,force_extras)


def fit_capacity(spectra_bits, frames, profile, extras, max_bytes, start, stop):
    """Preserved amplitude/position control from refine_speech_lpc.fit_capacity."""
    base=_base_bits(spectra_bits,frames,profile)
    capacity=extra_capacity(spectra_bits,frames,profile,max_bytes,len(extras))
    added=extras.copy();active=int(np.count_nonzero(added[:,1]));removed=0
    if active>capacity:
        choices=[i for i in range(start//40,len(added)) if added[i,1]]
        choices.sort(key=lambda i:(0 if i*40+int(added[i,0])>=stop else 1,
                                   0 if i*40<start+480 else 1,abs(int(added[i,1])),i))
        for i in choices[:active-capacity]:added[i]=(-1,0);removed+=1
        active-=removed
    enhanced=active>0
    bits=base+(frames*8+active*10 if enhanced else 0)
    size=22+(bits+7)//8
    return added,capacity,size,removed


def distortion_rate(score,file_bytes,rate_lambda=0.0):
    """D + lambda * R, with R in complete serialized bits (header/pad included)."""
    if isinstance(rate_lambda,bool) or not isinstance(rate_lambda,Real) or not math.isfinite(rate_lambda) or rate_lambda<0:
        raise ValueError('Expected finite nonnegative rate lambda')
    return score if not rate_lambda else score+rate_lambda*8*file_bytes


@dataclass
class AllocationResult:
    extras: np.ndarray
    pcm: np.ndarray
    stream: bytes | None
    feasible: bool
    status: str
    file_bytes: int
    payload_bits: int
    capacity: int
    removed: int
    evaluations: int
    score: int | float
    trace: list


def reclaim_extras(spectra,profile,extras,max_bytes,*,render,objective,start=0,
                   max_evaluations=4096,rate_lambda=0.0,serialize=None):
    """Greedy exact marginal removals, refreshing every score after each step.

    Every candidate is reconstructed through the caller's full output, including
    LPC/pitch/postfilter state. Only a complete round can choose a removal; an
    evaluation limit cannot silently turn a prefix of candidates into an exact
    minimum. A result with feasible=False is a bounded-search outcome for these
    fixed fields, never a proof that another v5 stream cannot fit.

    render(extras)->full PCM and objective(PCM)->finite scalar are required.
    serialize(extras)->bytes optionally verifies every measured size against the
    actual serializer. Callbacks receive owned copies. No input is mutated.
    """
    for name,value,low,high in (('max_bytes',max_bytes,22,65535),('start',start,0,64000),
                               ('max_evaluations',max_evaluations,1,10000000)):
        if isinstance(value,bool) or not isinstance(value,Integral) or not low<=value<=high:
            raise ValueError('Invalid '+name)
    if start%40:raise ValueError('Reclamation start must be aligned to40 samples')
    distortion_rate(0,0,rate_lambda)
    if not callable(render) or not callable(objective) or serialize is not None and not callable(serialize):
        raise ValueError('Expected render/objective and optional serialize callbacks')
    layout=bit_accounting(spectra,profile,extras);added=np.asarray(extras,np.int64).copy()
    capacity=extra_capacity(layout['spectrum_bits'],layout['frames'],profile,int(max_bytes),len(added))
    evaluations=0;trace=[];expected_samples=None
    def evaluate(candidate,cost):
        nonlocal evaluations,expected_samples
        pcm=np.asarray(render(candidate.copy())).copy()
        if (pcm.ndim!=1 or pcm.dtype.kind not in 'iu' or not len(pcm)
                or np.any(pcm<-32768) or np.any(pcm>32767)):
            raise ValueError('Renderer must return full PCM16 integers')
        if expected_samples is None:
            expected_samples=len(pcm)
            if not (layout['frames']-1)*320<expected_samples<=layout['frames']*320:
                raise ValueError('Renderer length differs from stored v5 frame geometry')
        elif len(pcm)!=expected_samples:raise ValueError('Renderer changed full PCM length')
        score=objective(pcm.copy())
        if isinstance(score,bool) or not isinstance(score,Real) or not math.isfinite(score):raise ValueError('Objective must return a finite scalar')
        score=int(score) if isinstance(score,Integral) else float(score)
        stream=None if serialize is None else bytes(serialize(candidate.copy()))
        if stream is not None and len(stream)!=cost['file_bytes']:raise AssertionError('V5 bit cost differs from actual serialization')
        evaluations+=1
        return pcm,score,stream
    pcm,score,stream=evaluate(added,layout)
    while layout['file_bytes']>max_bytes:
        choices=[i for i in range(start//40,len(added)) if added[i,1]]
        if not choices:status='no_removable_pulses';break
        if evaluations+len(choices)>max_evaluations:status='evaluation_limit';break
        best=None;cost=_layout(layout['spectrum_bits'],layout['frames'],profile,layout['extra_pulses']-1)
        for index in choices:
            trial=added.copy();trial[index]=(-1,0)
            trial_pcm,loss,trial_stream=evaluate(trial,cost)
            key=(distortion_rate(loss,cost['file_bytes'],rate_lambda),index)
            if best is None or key<best[0]:best=(key,index,trial,cost,trial_pcm,loss,trial_stream)
        _,index,trial,cost,trial_pcm,loss,trial_stream=best
        trace.append({'chunk':int(index),'position':int(added[index,0]),'amplitude':int(added[index,1]),
            'before_bytes':layout['file_bytes'],'after_bytes':cost['file_bytes'],
            'before_score':score,'after_score':loss,'marginal_distortion':loss-score,
            'marginal_rd':distortion_rate(loss,cost['file_bytes'],rate_lambda)-distortion_rate(score,layout['file_bytes'],rate_lambda),
            'round_evaluations':len(choices)})
        added=trial;layout=cost;pcm=trial_pcm;score=loss;stream=trial_stream
    else:status='fit'
    return AllocationResult(added,pcm,stream,layout['file_bytes']<=max_bytes,status,
        layout['file_bytes'],layout['payload_bits'],capacity,len(trace),evaluations,score,trace)
