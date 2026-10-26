"""Plot every paired corpus observation without hiding unchanged cases."""
import argparse,csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def run(table,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader(Path(table).open(encoding='utf-8')))
    rows=[r for r in rows if r['phase']=='aligned_pcm16' and r['stage']!='baseline']
    names=list(dict.fromkeys(r['case'] for r in rows));x=np.arange(len(names))
    fig,axes=plt.subplots(2,2,figsize=(18,10),sharex=True)
    for col,rate in enumerate(('12000','16000')):
        for stage,offset,color,label in [('enhanced',-.15,'#1767a6','Original bitrate ceiling'),('size_matched',.15,'#b05019','Original file-size cap')]:
            subset={r['case']:r for r in rows if r['ceiling_bps']==rate and r['stage']==stage}
            for ax,key in [(axes[0,col],'ser_delta_db'),(axes[1,col],'stoi_delta')]:
                y=[float(subset[name][key]) if subset[name][key] else np.nan for name in names]
                ax.scatter(x+offset,y,s=25,color=color,label=label)
                ax.vlines(x+offset,0,y,color=color,alpha=.4,lw=1)
        axes[0,col].set_title(f'{int(rate)//1000} kbit/s audio ceiling')
        for ax in axes[:,col]:
            ax.axhline(0,color='black',lw=.8);ax.grid(axis='y',alpha=.2)
            ax.set_xticks(x,names,rotation=75,ha='right',fontsize=8)
        axes[0,col].set_ylabel('SER gain (dB); silence/perfect shown in CSV')
        axes[1,col].set_ylabel('STOI gain; speech only')
    axes[0,0].legend(loc='upper left');fig.suptitle('LPX two-seed search versus original joint: all 27 cases\nPCM16 / 8 kHz, unchanged decoder, full 4-second references; no loudness normalization')
    fig.tight_layout();fig.savefig(output/'paired-gains.png',dpi=150);fig.savefig(output/'paired-gains.svg');plt.close(fig)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('table',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args();run(a.table,a.output)
