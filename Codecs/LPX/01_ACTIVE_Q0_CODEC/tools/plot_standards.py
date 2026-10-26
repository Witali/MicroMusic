#!/usr/bin/env python3
"""Standalone plots of measured codec errors and rate-cap feasibility."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def run(summary_path,output):
    summary=json.loads(Path(summary_path).read_text());output=Path(output);output.mkdir(parents=True,exist_ok=True)
    order=('LPX','opus_audio','opus_voip','vorbis','speex_abr','speex_cbr_under')
    names=('LPX','Opus audio','Opus VoIP','Vorbis','Speex ABR','Speex CBR')
    colors=('#2563eb','#ea580c','#fbbf24','#16a34a','#8b5cf6','#a78bfa')
    group=next(g for g in summary['rate_groups'] if g['group']=='clean' and g['ceiling_bps']==24000)
    values=[group['codecs'][k]['aligned_pcm16'] for k in order]
    labels=[f'{name} ({v["audio_kbps_mean"]:.1f} kb/s)' for name,v in zip(names,values)]
    y=np.arange(len(order));fig,axes=plt.subplots(1,3,figsize=(13.5,4.5),sharey=True)
    for ax,field,title in ((axes[0],'ser_aggregate_db','SER, dB (higher is closer)'),
                          (axes[1],'worst_max_abs_error_pcm16','Worst |error|, % full scale (lower)')):
        data=[v[field] if field!='worst_max_abs_error_pcm16' else v[field]*100/32768 for v in values]
        ax.barh(y,data,color=colors,height=.62);ax.set_title(title,fontsize=10)
        ax.set_xlim(0,max(data)*1.2)
        for row,value in enumerate(data):ax.text(value+max(data)*.025,row,f'{value:.2f}',va='center',fontsize=9)
        ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    axes[2].scatter([v['stoi_mean'] for v in values],y,c=colors,s=65)
    axes[2].set_title('STOI intelligibility (not MOS)',fontsize=10);axes[2].set_xlim(.93,1.008)
    for row,v in enumerate(values):axes[2].text(v['stoi_mean']+.0014,row,f'{v["stoi_mean"]:.4f}',va='center',fontsize=9)
    axes[2].grid(axis='x',alpha=.2);axes[0].set_yticks(y,labels);axes[0].invert_yaxis()
    fig.suptitle('16 speech clips, 4 seconds each, mono 8 kHz — common audio-packet ceiling 24 kb/s',fontsize=12)
    fig.text(.5,.015,'Whole-reference PCM16 before PWM; integer delay compensation; no gain fitting. Actual rates are shown in labels.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,.93));fig.savefig(output/'quality-24k.png',dpi=150);plt.close(fig)
    counts=np.asarray([[next(g for g in summary['rate_groups'] if g['group']=='clean' and g['ceiling_bps']==r)['codecs'][c]['aligned_pcm16']['encoded_cases']
                        for r in (8000,12000,16000,24000)] for c in order])
    fig,ax=plt.subplots(figsize=(8,4.5));ax.imshow(counts,vmin=0,vmax=16,cmap='YlGn',aspect='auto')
    ax.set_xticks(range(4),('8','12','16','24'));ax.set_yticks(range(6),names)
    for row in range(6):
        for col in range(4):ax.text(col,row,f'{counts[row,col]}/16',ha='center',va='center',color='white' if counts[row,col]>=12 else 'black')
    ax.set_xlabel('Audio-packet ceiling, kb/s');ax.set_title('Speech inputs fitting the actual byte cap')
    fig.text(.5,.015,'Bounded encoder profiles; no-fit is not a format minimum. The counted 80ms flush tail and packet padding affect exact caps.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.06,1,1));fig.savefig(output/'rate-feasibility.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('summary',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args();run(a.summary,a.output)
