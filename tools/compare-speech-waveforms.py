"""Compare whole waveforms and automatically selected periodic voice windows.

Local phase alignment is a diagnostic only; it never changes exported audio.
The report separates same-clock error, best local lag and remaining shape error.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, find_peaks, sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from spectrogram_objective import SpectrogramObjective


def correlation(x, y):
    x,y=x-x.mean(),y-y.mean()
    return float(np.dot(x,y)/(np.linalg.norm(x)*np.linalg.norm(y)+1e-20))


def windows(reference, start, sr):
    low=sosfilt(butter(2,1500,fs=sr,output='sos'),reference)
    candidates=[]
    for centre in range(max(start+384,384),len(reference)-384,128):
        chunk=low[centre-256:centre+256]
        ac=np.array([correlation(chunk[lag:],chunk[:-lag]) for lag in range(12,127)])
        peaks=find_peaks(ac)[0]
        if not len(peaks):continue
        best=float(ac[peaks].max())
        selected=peaks[ac[peaks]>=best*.95]
        lag=int(selected[0])+12
        rms=float(np.sqrt(np.mean(chunk*chunk)))
        candidates.append((best*rms,centre,lag,best))
    chosen=[]
    for item in sorted(candidates,reverse=True):
        if all(abs(item[1]-other[1])>=round(.3*sr) for other in chosen):chosen.append(item)
        if len(chosen)==3:break
    return sorted(chosen,key=lambda item:item[1])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--candidate',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--label',default='Candidate',help='Name used for the decoded waveform')
    p.add_argument('--start-sample',type=int,default=0,help='Start of voice region for automatic diagnostic windows')
    a=p.parse_args()
    reference,sr=sf.read(a.reference)
    objective=SpectrogramObjective(reference,sr)
    spec=importlib.util.spec_from_file_location('wave_reader',ROOT/'tools/compare-speech-spectrograms.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    candidate,rate=helper.read_candidate(a.candidate,len(reference),sr)
    if rate!=sr or not 0<=a.start_sample<len(reference)-1024:p.error('Invalid sample rate or voice start')
    x,y=objective.filtered,objective.matched(candidate)
    a.output.mkdir(parents=True,exist_ok=True)
    t=np.arange(len(x))/sr
    fig,axes=plt.subplots(2,1,figsize=(14,6),sharex=True)
    fig.subplots_adjust(left=.08,right=.98,top=.94,bottom=.11,hspace=.28)
    for data,label,color in ((x,'Original','#777'),(y,a.label,'#166fa7')):
        axes[0].plot(t,data,label=label,color=color,alpha=.7,linewidth=.5)
        envelope=np.sqrt(np.convolve(data*data,np.ones(128)/128,mode='same'))
        axes[1].plot(t,envelope,label=label,color=color)
    axes[0].set(ylabel='Signed amplitude',title='Same 70 Hz highpass and one global RMS match')
    axes[1].set(ylabel='17 ms RMS envelope',xlabel='Time, seconds')
    for ax in axes:ax.legend();ax.grid(alpha=.2)
    fig.savefig(a.output/'waveforms.png',dpi=125);plt.close(fig)
    chosen=windows(x,a.start_sample,sr)
    if not chosen:raise ValueError('No nonempty periodicity diagnostic window')
    fig,axes=plt.subplots(len(chosen),2,figsize=(14,3*len(chosen)),squeeze=False)
    fig.subplots_adjust(left=.07,right=.98,top=.94,bottom=.09,hspace=.42,wspace=.18)
    details=[]
    for row,(_,centre,period,periodicity) in enumerate(chosen):
        length=max(128,min(384,period*4));left=centre-length//2;right=left+length
        ref=x[left:right];same=y[left:right]
        scores=[(correlation(ref,y[left+lag:right+lag]),lag) for lag in range(-period,period+1)]
        corr,lag=max(scores)
        aligned=y[left+lag:right+lag]
        gain=float(np.dot(ref,aligned)/(np.dot(aligned,aligned)+1e-20))
        item=dict(start_seconds=left/sr,end_seconds=right/sr,period_samples=period,
            periodicity_estimate=periodicity,same_clock_correlation=correlation(ref,same),
            best_phase_lag_samples=lag,phase_aligned_correlation=corr,
            phase_aligned_relative_rmse=float(np.linalg.norm(ref-aligned)/(np.linalg.norm(ref)+1e-20)),
            local_gain_for_shape_diagnostic=gain,
            phase_and_local_gain_shape_rmse=float(np.linalg.norm(ref-gain*aligned)/(np.linalg.norm(ref)+1e-20)))
        details.append(item)
        ms=np.arange(length)*1000/sr
        for col,data,title in ((0,same,'Same clock'),(1,aligned,f'Local phase shift {lag} samples; corr {corr:.2f}')):
            ax=axes[row,col];ax.plot(ms,ref,color='#777',label='Original');ax.plot(ms,data,color='#166fa7',alpha=.8,label=a.label)
            ax.set(title=f'{left/sr:.3f} s: {title}',xlabel='Window time, ms',ylabel='Amplitude')
            ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(a.output/'voice-periods.png',dpi=125);plt.close(fig)
    report=dict(processing='Identical 70 Hz highpass and one global RMS match. Local phase shifts are plots/diagnostics only.',
        schema='speech-waveform-diagnostic-v1',sample_rate=sr,samples=len(reference),voice_start_sample=a.start_sample,
        reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256(a.candidate.read_bytes()).hexdigest(),
        candidate_label=a.label,
        source_sha256_normalized_lf={str(path.relative_to(ROOT)).replace('\\','/'):
            hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for path in (Path(__file__),ROOT/'tools/compare-speech-spectrograms.py',
                         ROOT/'ATtiny13A/Sound/codec/spectrogram_objective.py')},
        raw_reference_mean=float(np.mean(reference)),raw_candidate_mean=float(np.mean(candidate)),
        windows=details,warning='Correlation is not a naturalness metric. Local lag/gain fitting does not change the audio or codec.')
    (a.output/'waveforms.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report))


if __name__=='__main__':main()
