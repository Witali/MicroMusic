#!/usr/bin/env python3
"""Inspect <=10 strongest original partial trajectories against WAV/AVR RAW."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from harmonic_tracks import HarmonicTrackObjective, VERSION


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def serial_tracks(tracks):
    return dict(times=tracks['times'].tolist(),count=tracks['count'].tolist(),
                track_id=tracks['track_id'].tolist(),amplitude=tracks['amplitude'].tolist(),
                frequency_hz=[[None if not np.isfinite(value) else float(value) for value in row]
                              for row in tracks['frequency_hz']])


def paths(ax,tracks,field,peak,*,color=None,alpha=1.,linewidth=1.):
    times = tracks['times']
    for track_id in np.unique(tracks['track_id']):
        if track_id < 0:
            continue
        rows,cols = np.where(tracks['track_id'] == track_id)
        values = np.full(len(times),np.nan)
        values[rows] = tracks[field][rows,cols]
        if field == 'amplitude':
            values[rows] = 20*np.log10(np.maximum(values[rows]/peak,1e-6))
        ax.plot(times,values,color=color or plt.get_cmap('tab10')(int(track_id)%10),
                alpha=alpha,linewidth=linewidth)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',action='append',required=True,help='Label=path.wav or Label=actual-avr.raw')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-tracks',type=int,default=10)
    p.add_argument('--n-fft',type=int,default=1024)
    p.add_argument('--hop',type=int,default=128)
    p.add_argument('--frequency-tolerance-cents',type=float,default=50.)
    p.add_argument('--frequency-tolerance-hz',type=float,default=0.)
    p.add_argument('--amplitude-tolerance-db',type=float,default=3.)
    a = p.parse_args()
    reference,sr = sf.read(a.reference,dtype='float64')
    objective = HarmonicTrackObjective(reference,sr,max_tracks=a.max_tracks,n_fft=a.n_fft,hop=a.hop,
        frequency_tolerance_cents=a.frequency_tolerance_cents,
        frequency_tolerance_hz=a.frequency_tolerance_hz,
        amplitude_tolerance_db=a.amplitude_tolerance_db)
    spec = importlib.util.spec_from_file_location('read_speech_candidate',ROOT/'tools/compare-speech-spectrograms.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    reference_tracks = objective.reference_tracks
    peak = max(float(reference_tracks['amplitude'].max()),1e-20)
    report = dict(version=VERSION,config=objective.config,reference_sha256=digest(a.reference),
                  samples=len(reference),sample_rate=sr,
                  processing='Same 70 Hz highpass, one global RMS match; unchanged timing; strongest local peaks, not F0 multiples',
                  missing_extra_note='Absolute errors describe matched partials only; missing/extra energy and coverage are mandatory companion metrics',
                  reference_tracks=serial_tracks(reference_tracks),candidates={})
    candidates = []
    for entry in a.candidate:
        if '=' not in entry:
            p.error('Each candidate must be Label=path')
        label,filename = entry.split('=',1)
        path = Path(filename)
        audio,rate = helper.read_candidate(path,len(reference),sr)
        if rate != sr:
            p.error('Candidate sample rate differs from reference')
        detail = objective.details(audio)
        candidates.append((label,detail))
        report['candidates'][label] = dict(sha256=digest(path),metrics=detail['metrics'],
            tracks=serial_tracks(detail['candidate_tracks']),matches=detail['matches'])
    a.output.mkdir(parents=True,exist_ok=True)
    fig,axes = plt.subplots(len(candidates)+1,2,figsize=(16,3.3*(len(candidates)+1)),
                            sharex=True,squeeze=False,layout='constrained')
    paths(axes[0,0],reference_tracks,'frequency_hz',peak)
    paths(axes[0,1],reference_tracks,'amplitude',peak)
    axes[0,0].set_title('Original: strongest <=10 partials at each time; colors follow track IDs')
    axes[0,1].set_title('Original partial levels; one shared dB reference')
    for row,(label,detail) in enumerate(candidates,1):
        tracks = detail['candidate_tracks']
        paths(axes[row,0],reference_tracks,'frequency_hz',peak,color='#aaaaaa',alpha=.5,linewidth=.7)
        paths(axes[row,1],reference_tracks,'amplitude',peak,color='#aaaaaa',alpha=.5,linewidth=.7)
        matched_reference,matched_candidate = set(),set()
        matched = {}
        for match in detail['matches']:
            frame,rid,cid = match['frame'],match['reference_id'],match['candidate_id']
            matched_reference.add((frame,rid));matched_candidate.add((frame,cid))
            if rid not in matched:
                matched[rid] = [np.full(len(tracks['times']),np.nan) for _ in range(2)]
            matched[rid][0][frame] = match['candidate_hz']
            matched[rid][1][frame] = 20*np.log10(max(match['candidate_amplitude']/peak,1e-6))
        for rid,values in matched.items():
            color = plt.get_cmap('tab10')(rid%10)
            for col in (0,1):
                axes[row,col].plot(tracks['times'],values[col],color=color,linewidth=1.1)
        for source,present,color,marker in ((reference_tracks,matched_reference,'#d32727','o'),
                                            (tracks,matched_candidate,'#ee8a00','x')):
            rows,cols = np.where(source['amplitude'] > 0)
            absent = [(r,c) for r,c in zip(rows,cols) if (int(r),int(source['track_id'][r,c])) not in present]
            if absent:
                rr,cc = np.asarray(absent).T
                axes[row,0].scatter(source['times'][rr],source['frequency_hz'][rr,cc],s=8,
                                     c=color,marker=marker,alpha=.45,linewidths=.6)
                axes[row,1].scatter(source['times'][rr],20*np.log10(np.maximum(source['amplitude'][rr,cc]/peak,1e-6)),
                                     s=8,c=color,marker=marker,alpha=.45,linewidths=.6)
        metrics = detail['metrics']
        axes[row,0].set_title(f"{label}: {metrics['frequency_error_cents']:.1f} cents mean; coverage {metrics['weighted_match_rate']:.1%}")
        axes[row,1].set_title(f"{metrics['level_error_db']:.1f} dB mean; missing {metrics['missing_reference_energy']:.1%}; extra {metrics['extra_candidate_energy']:.1%}")
    for row in range(len(axes)):
        axes[row,0].set(ylim=(0,3750),ylabel='Frequency (Hz)',xlim=(0,len(reference)/sr))
        axes[row,1].set(ylim=(-65,10),ylabel='Partial amplitude (dB / original peak)')
        for ax in axes[row]:
            ax.grid(alpha=.15)
    for ax in axes[-1]:
        ax.set_xlabel('Time (seconds)')
    axes[-1,0].legend(handles=[Line2D([],[],color='#aaa',label='Original track'),
        Line2D([],[],color='#3268aa',label='Matched output (original ID color)'),
        Line2D([],[],color='#d32727',marker='o',linestyle='',label='Missing original partial'),
        Line2D([],[],color='#ee8a00',marker='x',linestyle='',label='Extra output partial')],fontsize=8,loc='upper right')
    fig.savefig(a.output/'harmonic-tracks.png',dpi=125)
    plt.close(fig)
    sources = (Path(__file__),CODEC/'harmonic_tracks.py')
    report['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():
        hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources}
    (a.output/'harmonic-tracks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(config=objective.config,candidates={key:value['metrics'] for key,value in report['candidates'].items()})))


if __name__ == '__main__':
    main()
