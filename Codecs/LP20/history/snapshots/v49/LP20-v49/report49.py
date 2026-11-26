#!/usr/bin/env python3
"""Verify decoded waveform and collect all metrics; use unchanged v48 references."""
from refine49 import *
from scipy.signal import welch,stft
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def savecsv(p,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r));
 with p.open('w') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def run(c):
 base,d,meta,ref,lv,x=data(c);out=ROOT48/c;book=(base/'book.bin').read_bytes();n=len(x);rows=[];old=list(csv.DictReader((V48/'selected.csv').open()));old=[dict(r,profile='v48 '+r['selection']) for r in old if r['clip']==c]
 for r0 in old:rows.append(r0)
 for p in sorted(out.glob('*.lp4v')):
  if p.stem.startswith(('Viterbi-','Blend-')):
   z,_,_=decode_v(p,book);a=render(z,d,meta);assert np.array_equal(a,wavfile.read(p.with_suffix('.wav'))[1]);assert p.stat().st_size<=int(n*6000/(8*FS));r=json.loads(p.with_suffix('.json').read_text());r['verified']=True;rows.append(r)
 for label,tag in [('Quality','Blend-2'),('MaxSNR','Viterbi-base-6k'),('Compact59','Viterbi-spectral-5.9k')]:
  for ext in ('.wav','.lp4v'):shutil.copy2(out/(tag+ext),out/(label+ext))
  print(c,label,next(r['snr_db'] for r in rows if r['profile']==tag),flush=True)
 for src,dst in [(base/'reference.wav','reference.wav'),(base/'book.bin','book.bin'),(base/'dds.bin','dds.bin'),(V48/c/'Recommended.wav','v48.wav')]:shutil.copy2(src,out/dst)
 r=filt(ref.astype(float)/32768);r-=r.mean();labels=['Reference','v48 Recommended','v49 Quality','v49 Compact59'];ys=[r]+[align(r,filt(wavfile.read(out/f)[1].astype(float)/32768))[0] for f in ('v48.wav','Quality.wav','Compact59.wav')]
 i=int(np.argmax(abs((ys[1]-r)[480:-480])))+480;lo=max(0,i-480);hi=min(len(r),i+480);t=np.arange(lo,hi)/48
 fig,axs=plt.subplots(2,1,figsize=(10,5.5),sharex=True,layout='constrained');axs[0].plot(t,r[lo:hi],label=labels[0],linewidth=1.5)
 for label,y in zip(labels[1:],ys[1:]):axs[0].plot(t,y[lo:hi],label=label,linewidth=.9);axs[1].plot(t,100*(y-r)[lo:hi]/np.max(abs(r)),label=label,linewidth=.9)
 axs[1].axhline(8,ls='--',alpha=.4);axs[1].axhline(-8,ls='--',alpha=.4);axs[0].set_ylabel('Amplitude');axs[1].set_ylabel('Error (% reference peak)');axs[1].set_xlabel('Time (ms)')
 for ax in axs:ax.grid(alpha=.2);ax.legend()
 fig.savefig(out/'peak-detail.png',dpi=150);plt.close(fig)
 fig,ax=plt.subplots(figsize=(9,4.6),layout='constrained')
 for label,y in zip(labels[1:],ys[1:]):
  f,p=welch((y-r)[480:-480],48000,nperseg=4096,noverlap=2048);mask=f<=3500;ax.plot(f[mask],10*np.log10(np.maximum(p[mask],1e-20)),label=label)
 ax.set(xlabel='Frequency (Hz)',ylabel='Error PSD (dB/Hz)',title='LP20 PWM: error spectrum');ax.legend();ax.grid(alpha=.2);fig.savefig(out/'error-spectrum.png',dpi=150);plt.close(fig)
 start=max(0,min(len(r)-144000,i-72000));end=start+144000;scale=.90/max(float(np.max(abs(a[start:end]))) for a in ys);ab=np.concatenate([v for a in ys for v in (a[start:end]*scale,np.zeros(16800))]);wavfile.write(out/'AB.wav',48000,np.clip(np.rint(ab*32767),-32768,32767).astype(np.int16))
 fig,axs=plt.subplots(len(ys),1,figsize=(10,2*len(ys)),sharex=True,sharey=True,layout='constrained');vmax=None
 for ax,a,label in zip(axs,ys,labels):
  f,t,S=stft(a[start:end],48000,nperseg=1024,noverlap=832);mask=f<=3500;D=20*np.log10(np.maximum(abs(S[mask]),1e-8));vmax=float(D.max()) if vmax is None else vmax;im=ax.pcolormesh(t+start/48000,f[mask],D,shading='auto',vmin=vmax-65,vmax=vmax);ax.set_ylabel('Hz');ax.set_title(label,loc='left',fontsize=10)
 axs[-1].set_xlabel('Time (s)');fig.colorbar(im,ax=axs,label='Magnitude (dB)');fig.savefig(out/'spectrogram.png',dpi=125);plt.close(fig)
 direct=json.loads((out/'direct.json').read_text());dr=[dict(clip=c,profile='v48 Quad',**direct['baseline'])]+[dict(clip=c,profile=f'Viterbi {r["states"]} states',**r) for r in direct['passes']]+[dict(clip=c,profile='Quad control '+str(r['passno']),**r) for r in json.loads((out/'quad-control.json').read_text())]+[dict(clip=c,profile='Viterbi 729 states',**r) for r in json.loads((out/'direct-729.json').read_text())]
 return rows,dr
if __name__=='__main__':
 rows=[];dr=[]
 for c in ('first','second'):
  a,b=run(c);rows+=a;dr+=b
 savecsv(ROOT48/'comparison.csv',rows);savecsv(ROOT48/'direct.csv',dr)
