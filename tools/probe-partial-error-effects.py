#!/usr/bin/env python3
"""Controlled PC partial detuning versus partial-level errors on arbitrary speech.

Every transformation keeps the same sample count and original residual signal.
This is a diagnostic stimulus study, not a codec fit or an AVR size claim.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import hilbert, istft, stft
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from harmonic_tracks import HarmonicTrackObjective
from spectrogram_objective import SpectrogramObjective
from auto_encoder import SpectralObjective
from hq4_speech_search import deterministic_estoi


def components(reference, objective):
    """Disjoint soft peak-cluster masks with an exact additive residual.

    Each selected local peak gets a flat +-2-bin complex-STFT mask, tapering
    to zero at +-3 bins. Removing its full main lobe reduces coherent leftover
    energy in the residual, which would otherwise beat against a detuned part.
    Overlapping masks share bins without exceeding unity total ownership.
    Original phases remain in every component. No reference interval or
    source frequency is selected manually.
    """
    sr,n_fft,hop = objective.sr,objective.n_fft,objective.hop
    frequencies,times,z = stft(reference,fs=sr,window='hann',nperseg=n_fft,
                              noverlap=n_fft-hop,boundary='zeros',padded=True)
    tracks = objective.reference_tracks
    entries,total = {},np.zeros(z.shape,dtype=float)
    for frame in range(len(times)):
        for column in np.flatnonzero(tracks['amplitude'][frame] > 0):
            track_id = int(tracks['track_id'][frame,column])
            centre = tracks['frequency_hz'][frame,column]/objective.bin_hz
            bins = np.arange(max(0,int(np.floor(centre))-3),min(len(frequencies),int(np.floor(centre))+5))
            weight = np.minimum(1.,np.maximum(0.,3-abs(bins-centre)))
            keep = weight > 0
            bins,weight = bins[keep],weight[keep]
            entries.setdefault(track_id,[]).append((frame,bins,weight))
            total[bins,frame] += weight
    denominator = np.maximum(total,1.)
    partials = []
    periodic = np.zeros(len(reference))
    for track_id,locations in sorted(entries.items()):
        selected = np.zeros(z.shape,dtype=complex)
        for frame,bins,weight in locations:
            selected[bins,frame] = z[bins,frame]*weight/denominator[bins,frame]
        restored = istft(selected,fs=sr,window='hann',nperseg=n_fft,noverlap=n_fft-hop,
                         boundary=True)[1][:len(reference)]
        rows,cols = np.where(tracks['track_id'] == track_id)
        frequency = np.interp(np.arange(len(reference))/sr,times[rows],tracks['frequency_hz'][rows,cols])
        start = max(0,int(times[int(rows[0])]*sr)-n_fft//2)
        analytic = hilbert(np.pad(restored,(n_fft,n_fft)))[n_fft:-n_fft]
        partials.append(dict(track_id=track_id,signal=restored,analytic=analytic,
                             frequency=frequency,start_sample=start))
        periodic += restored
    residual = reference-periodic
    identity = residual+sum((part['signal'] for part in partials),np.zeros(len(reference)))
    return partials,residual,identity


def perturb(partials,residual,sr,*,cents=0.,db=0.):
    output = residual.copy()
    for part in partials:
        sign = 1. if part['track_id']%2 == 0 else -1.
        if cents:
            change = part['frequency']*(2**(sign*cents/1200)-1)
            angle = np.r_[0.,np.cumsum(change[:-1])]*2*np.pi/sr
            angle -= angle[part['start_sample']]
            value = np.real(part['analytic']*np.exp(1j*angle))
        else:
            value = part['signal']
        output += value*10**(sign*db/20)
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    reference,sr = sf.read(a.reference,dtype='float64')
    tracks = HarmonicTrackObjective(reference,sr)
    spectrum = SpectrogramObjective(reference,sr)
    legacy = SpectralObjective(reference,sr)
    partials,residual,identity = components(reference,tracks)
    error = float(np.max(abs(identity-reference)))
    if error > 1e-12:
        raise AssertionError('Identity component/residual reconstruction changed the recording')
    conditions = [('identity',identity,dict(cents=0.,db=0.))]
    conditions += [(f'frequency-{cents}c',perturb(partials,residual,sr,cents=cents),dict(cents=cents,db=0.))
                   for cents in (10,25,50)]
    conditions += [(f'level-{db}db',perturb(partials,residual,sr,db=db),dict(cents=0.,db=db))
                   for db in (1,3,6)]
    a.output.mkdir(parents=True,exist_ok=True)
    report = dict(schema='partial-error-effects-v1',sample_rate=sr,samples=len(reference),
        reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
        tracks_config=tracks.config,partial_ids=len(partials),identity_max_abs_error=error,
        component_mask='Disjoint flat +-2-bin peak-cluster masks tapering to zero at +-3 bins; original complex phases',
        frequency_method='Analytic per-track phase modulation, integral of signed cents-derived frequency offset',
        sign_method='Fixed alternating +/- signs by stable track ID, shared by frequency and level experiments',
        residual_method='Original minus sum(partials), unchanged before one common global RMS treatment',
        causal_scope='Constructed PC stimuli; small cross-effects from finite-window partial separation are measured, not assumed absent',
        avr_assembled=False,hardware_verified=False,codec_fit=False,conditions={})
    signals = [('original',reference)]
    for name,audio,settings in conditions:
        sf.write(a.output/(name+'.wav'),audio,sr,subtype='FLOAT')
        report['conditions'][name] = dict(settings=settings,stoi=float(stoi(reference,audio,sr)),
            estoi=deterministic_estoi(reference,audio,sr),
            **legacy.spectrum(audio),**spectrum.evaluate(audio),**tracks.evaluate(audio))
        signals.append((name,audio))
    matched = {name:spectrum.matched(audio) for name,audio in signals}
    scale = .85/max(float(np.max(abs(audio))) for audio in matched.values())
    order = ('original','identity','frequency-25c','level-3db')
    sf.write(a.output/'comparison.wav',np.concatenate([np.r_[matched[name]*scale,np.zeros(round(.3*sr))]
                                                      for name in order]),sr,subtype='PCM_16')
    report['listening_order'] = list(order)
    report['listening_processing'] = 'Identical 70 Hz highpass, one global RMS match, shared peak scale'
    sources = [Path(__file__),CODEC/'harmonic_tracks.py',CODEC/'spectrogram_objective.py',
               CODEC/'auto_encoder.py',CODEC/'hq4_speech_search.py']
    report['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():
        hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources}
    report['runtime'] = {name:importlib.metadata.version(name) for name in ('numpy','scipy','pystoi','soundfile')}
    report['runtime']['python'] = sys.version.split()[0]
    (a.output/'quality.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    labels = [name for name,audio,settings in conditions]
    fig,axes = plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,key,title in zip(axes.ravel(),('frequency_error_cents','level_error_db','stoi','estoi'),
                           ('Measured frequency error (cents)','Measured partial level error (dB)','STOI','eSTOI')):
        values = [report['conditions'][name][key] for name in labels]
        ax.bar(np.arange(len(labels)),values,color=['#888']+['#387aba']*3+['#dd8b37']*3)
        ax.set_xticks(np.arange(len(labels)),labels,rotation=25,ha='right')
        ax.set_title(title);ax.grid(axis='y',alpha=.2)
        if key in ('stoi','estoi'):
            ax.set_ylim(max(0.,min(values)-.05),1.01)
    fig.savefig(a.output/'partial-error-effects.png',dpi=140)
    plt.close(fig)
    fig,axes = plt.subplots(4,1,figsize=(13,10),sharex=True,sharey=True,layout='constrained')
    maximum = max(float(spectrum.magnitude(matched['original'])[2].max()),1e-20)
    for ax,name in zip(axes,order):
        f,t,mag = spectrum.magnitude(matched[name],1024,128)
        shown = ax.pcolormesh(t,f,20*np.log10(np.maximum(mag/maximum,1e-6)),
                             cmap='magma',shading='auto',vmin=-65,vmax=0)
        ax.set(title=name,ylabel='Frequency (Hz)',ylim=(0,3750))
    axes[-1].set_xlabel('Time (seconds)')
    fig.colorbar(shown,ax=axes,label='dB / original peak',shrink=.85)
    fig.savefig(a.output/'spectrograms.png',dpi=140)
    plt.close(fig)
    print(json.dumps(dict(identity_max_abs_error=error,partial_ids=len(partials),
                         conditions=report['conditions'])),flush=True)


if __name__ == '__main__':
    main()
