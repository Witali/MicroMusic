#!/usr/bin/env python3
"""Verify complete LP4V streams, compare output waveforms, and select Pareto profiles."""
from grid51 import *
import csv,shutil
from scipy.signal import welch,stft
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def report(c):
 d,m,r,z=s50.load(c);out=ROOT/c;p=grid();src=BASE51/'LP20-v50'/c;book=(src/'book.bin').read_bytes();prev=json.loads((src/'selected.json').read_text());rows=[];ys={}
 x=filt(r.astype(float)/32768);x-=x.mean();duration=len(z)/s50.FS
 for label,key,wname in [('v49','v49','v49.wav'),('v50','255-power1.7','255-power1.7.wav')]:
  a=next(q for q in prev if q['profile']==key);a=dict(a,profile=label,bytes=(src/'Quality.lp4v').stat().st_size);rows.append(a);ys[label]=align(x,filt(wavfile.read(src/wname)[1].astype(float)/32768))[0]
 candidates=[]
 for f in sorted(out.glob('Peak*.lp4v')):
  q=f.with_suffix('.json');assert q.exists(),f;row=json.loads(q.read_text());zz,frames,bits=s50.decode_v(f,book);assert len(zz)==len(z);w=render_new(zz,d,p);assert np.array_equal(w,wavfile.read(f.with_suffix('.wav'))[1]),f;assert f.stat().st_size==row['bytes'] and f.stat().st_size*8/duration/1000<=6;row['verified']=True;rows.append(row);candidates.append(row)
 good=[a for a in candidates if a['peak_error_pct']<=8 and a['p999_pct']<=3.5]
 best=max(good,key=lambda a:a['snr_db']);compact=max([a for a in good if a['kbps']<=5.9],key=lambda a:a['snr_db']);selected=[]
 for name,rr in [('Quality',best),('Compact59',compact)]:
  a=dict(rr,selection=name);selected.append(a)
  for ext in ('.lp4v','.wav'):shutil.copyfile(out/(rr['profile']+ext),out/(name+ext))
  ys[name]=align(x,filt(wavfile.read(out/(name+'.wav'))[1].astype(float)/32768))[0]
 shutil.copyfile(src/'reference.wav',out/'reference.wav');shutil.copyfile(src/'book.bin',out/'book.bin');shutil.copyfile(src/'dds.bin',out/'dds.bin')
 for name,rr in [('Quality',best),('Compact59',compact)]:print(c,name,rr['profile'],rr['snr_db'],rr['kbps'],rr['peak_error_pct'],flush=True)
 fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained');ax.set(xlabel='Frequency (Hz)',ylabel='Error PSD (dB/Hz)',title='LP20 v51: error spectra after modeled PWM')
 for k,y in ys.items():
  f,ps=welch((y-x)[480:-480],48000,nperseg=4096);b=f<=3500;ax.plot(f[b],10*np.log10(np.maximum(ps[b],1e-20)),label=k)
 ax.legend();ax.grid(alpha=.2);fig.savefig(out/'error-spectrum.png',dpi=145);plt.close(fig)
 i=np.argmax(abs((ys['v50']-x)[480:-480]))+480;lo=max(0,i-480);hi=min(len(x),i+480);t=np.arange(lo,hi)/48
 fig,axs=plt.subplots(2,1,figsize=(10,5.5),sharex=True,layout='constrained');axs[0].plot(t,x[lo:hi],label='Reference',lw=1.5)
 for k,y in ys.items():axs[0].plot(t,y[lo:hi],label=k,lw=.9);axs[1].plot(t,100*(y-x)[lo:hi]/max(abs(x)),label=k,lw=.9)
 axs[0].set_ylabel('Amplitude');axs[1].set_ylabel('Error (% reference peak)');axs[1].set_xlabel('Time (ms)');axs[1].axhline(8,ls='--',alpha=.5);axs[1].axhline(-8,ls='--',alpha=.5)
 for ax in axs:ax.legend();ax.grid(alpha=.2)
 fig.savefig(out/'peak-detail.png',dpi=145);plt.close(fig)
 # identical window, color scale, and frequency range.
 start=max(0,min(len(x)-144000,i-72000));end=start+144000
 seg=[x[start:end],ys['v49'][start:end],ys['v50'][start:end],ys['Quality'][start:end],ys['Compact59'][start:end]]
 fig,axs=plt.subplots(5,1,figsize=(9,9),sharex=True,sharey=True,layout='constrained');titles=['Reference','v49','v50','v51 Quality','v51 Compact59'];st=[stft(a,48000,nperseg=1024,noverlap=768) for a in seg];scale=max(np.max(abs(s[2])) for s in st)
 for ax,title,(f,t,S) in zip(axs,titles,st):
  mask=f<=3500;mesh=ax.pcolormesh(t,f[mask],20*np.log10(np.maximum(abs(S[mask])/scale,1e-5)),vmin=-65,vmax=0,shading='auto');ax.set_title(title,loc='left',fontsize=10);ax.set_ylabel('Hz')
 axs[-1].set_xlabel('Time in excerpt (s)');fig.colorbar(mesh,ax=axs,label='dB, common reference');fig.savefig(out/'spectrogram.png',dpi=145);plt.close(fig)
 scale=.9/max(np.max(abs(a)) for a in seg);ab=np.concatenate([v for a in seg for v in (a*scale,np.zeros(16800))]);wavfile.write(out/'AB.wav',48000,np.clip(np.rint(ab*32767),-32768,32767).astype(np.int16))
 return rows,selected
if __name__=='__main__':
 rows=[];selected=[]
 for c in ('first','second'):
  a,b=report(c);rows+=a;selected+=b
 for name,rs in [('comparison',rows),('selected',selected)]:
  with (ROOT/(name+'.csv')).open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for a in rs for k in a)));w.writeheader();w.writerows(rs)
