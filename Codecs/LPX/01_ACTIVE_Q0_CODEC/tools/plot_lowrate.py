"""Plot one frozen common speech cohort; missing LPX budgets remain missing."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from summarize_lowrate import aggregate


def run(measurements,baseline,output):
    data=json.loads(Path(measurements).read_text(encoding='utf-8'));old=json.loads(Path(baseline).read_text(encoding='utf-8'))
    common=[c['id'] for c in data['cases'] if c['group']=='clean' and next(r for r in c['rates'] if r['ceiling_bps']==16000)['baseline']['status']=='ok']
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(11,4.6))
    specs=[('LPX before','LPX','#777777','o'),('LPX target','target_budget','#e69f00','s'),
           ('LPX joint','joint','#1765e8','o'),('LPX perceptual','perceptual','#7a3db8','x'),
           ('Opus audio','opus_audio','#009e73','^'),('Vorbis','vorbis','#d55e00','v'),('Speex CBR','speex_cbr_under','#56b4e9','d')]
    for label,codec,color,marker in specs:
        points=[]
        for rate in (12000,16000,24000):
            rows=[]
            for name in common:
                case=next(c for c in (data if codec in ('target_budget','joint','perceptual') else old)['cases'] if c['id']==name)
                rate_row=next((r for r in case['rates'] if r['ceiling_bps']==rate),None)
                if rate_row and codec in rate_row:rows.append((name,rate_row[codec]))
            if len(rows)==len(common) and all(r['status']=='ok' for _,r in rows):
                m=aggregate(rows);points.append(m)
        if not points:continue
        for ax,field in zip(axes,('stoi_mean','ser_aggregate_db')):
            ax.plot([p['audio_kbps_mean'] for p in points],[p[field] for p in points],color=color,marker=marker,label=label)
    axes[0].set_ylabel('Mean STOI (not MOS)');axes[0].set_ylim(.55,1.005)
    axes[1].set_ylabel('Energy-aggregate SER, dB')
    for ax in axes:ax.set_xlabel('Actual audio-packet bitrate, kb/s');ax.grid(alpha=.2)
    axes[1].legend(fontsize=8,loc='best')
    fig.suptitle(f'Same {len(common)} speech clips at every plotted point; whole 4s PCM16 before PWM')
    fig.text(.5,.01,'Fixed old-16k-fit cohort. Standard-codec points reuse the previous pinned FFmpeg run; counts, actual rates and setup overhead are reported separately.',ha='center',fontsize=7)
    fig.tight_layout(rect=(0,.05,1,.94));fig.savefig(output/'quality-bitrate.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('measurements','baseline','output'):ap.add_argument(name,type=Path)
    a=ap.parse_args();run(a.measurements,a.baseline,a.output)
