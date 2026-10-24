"""Decompose the installed standard STOI into its actual octave-band scores.

This is analysis only. The scalar is checked against pystoi itself. Segment
indices refer to the signal after silence removal, not original timestamps.
"""
import importlib
import numpy as np


def band_scores(reference,candidate,sample_rate):
    api=importlib.import_module('pystoi.stoi');u=api.utils
    x=np.asarray(reference,dtype=float);y=np.asarray(candidate,dtype=float)
    if x.ndim!=1 or x.shape!=y.shape or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError('Expected complete finite equal-length mono signals')
    original_x,original_y=x,y
    if sample_rate!=api.FS:
        x=u.resample_oct(x,api.FS,sample_rate);y=u.resample_oct(y,api.FS,sample_rate)
    x,y=u.remove_silent_frames(x,y,api.DYN_RANGE,api.N_FRAME,api.N_FRAME//2)
    envelope=[]
    for signal in (x,y):
        spectrum=u.stft(signal,api.N_FRAME,api.NFFT,overlap=2).T
        envelope.append(np.sqrt(api.OBM@abs(spectrum)**2))
    frames=envelope[0].shape[1]
    if frames<api.N:raise ValueError('Too few retained frames to decompose STOI')
    segments=[np.stack([e[:,end-api.N:end] for end in range(api.N,frames+1)]) for e in envelope]
    a,b=segments
    b=b*(np.linalg.norm(a,axis=2,keepdims=True)/(np.linalg.norm(b,axis=2,keepdims=True)+u.EPS))
    b=np.minimum(b,a*(1+10**(-api.BETA/20)))
    a=a-a.mean(axis=2,keepdims=True);b=b-b.mean(axis=2,keepdims=True)
    a=a/(np.linalg.norm(a,axis=2,keepdims=True)+u.EPS)
    b=b/(np.linalg.norm(b,axis=2,keepdims=True)+u.EPS)
    correlations=np.sum(a*b,axis=2);actual=float(api.stoi(original_x,original_y,sample_rate))
    if not np.isclose(correlations.mean(),actual,rtol=0,atol=1e-12):
        raise AssertionError('Band decomposition differs from installed STOI')
    mean=correlations.mean(axis=0)
    return dict(stoi=actual,bands=[dict(center_hz=float(f),correlation=float(q),
        contribution_to_unit_gap=float((1-q)/len(mean))) for f,q in zip(api.CF,mean)],
        retained_stft_frames=frames,segments=len(correlations),
        segment_correlations=correlations.mean(axis=1).tolist(),
        segment_time_axis='Indices after original-driven silence removal; not source timestamps')
