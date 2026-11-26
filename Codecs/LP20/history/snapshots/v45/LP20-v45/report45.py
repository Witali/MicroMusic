from adaptive45 import *
from peak_audit import filt,align
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import stft
import csv
allrows=[];selected=[]
for clip in ('first','second'):
    src=BASE/'input'/clip;out=ROOT/clip
    old=next(r for r in json.load(open(BASE/clip/'rd_results.json')) if r['profile']=='6k-SNR');old['profile']='v44 Strict6';allrows.append(old);selected.append(old)
    for fn in ('results.json','ablation.json','refit.json'):
        rr=json.load(open(out/fn));allrows+=rr
        selected += [r for r in rr if r['profile'] in ('fixed-control','joint256-tight','adaptive-tight','adaptive-refit','adaptive58-tight','adaptive-refit-peak')]
    # Validate selected streams again; render regenerated from the byte stream.
    d=dict(np.load(src/'model.npz'));meta=json.loads((src/'decoder.json').read_text());book=(src/'book.bin').read_bytes();ref=wavfile.read(src/'reference.wav')[1];x=filt(ref.astype(float)/32768);x-=x.mean();ys={}
    for label,p in [('v44 Strict6',BASE/clip/'6k-SNR.wav'),('v45 6k',out/'adaptive-refit.wav'),('v45 5.8k',out/'adaptive58-tight.wav')]:
        wav=wavfile.read(p)[1];v=filt(wav.astype(float)/32768);y,_,_=align(x,v);ys[label]=y
        if label.startswith('v45'):
            tag='adaptive-refit' if label.endswith('6k') else 'adaptive58-tight';z,_,_=decode_v(out/(tag+'.lp4v'),book);assert np.array_equal(render(z,d,meta),wav)
    # An active voiced waveform segment, same range / time on every panel.
    N=960;u=x[:len(x)//N*N].reshape(-1,N);pow=np.mean(u*u,axis=1);rank=np.argsort(pow)[::-1];t0=0
    for i in rank:
        if i>50 and i<len(u)-50:t0=max(0,i*N-480);break
    ix=slice(t0,t0+1920);t=np.arange(t0,t0+1920)*1000/48000;fig,ax=plt.subplots(3,1,figsize=(10,7),sharex=True,sharey=True)
    for a,(name,y) in zip(ax,ys.items()):a.plot(t,x[ix],label='Reference',alpha=.65);a.plot(t,y[ix],label=name,linewidth=1);a.set_ylabel('Amplitude');a.grid(alpha=.2);a.legend(loc='upper right')
    ax[-1].set_xlabel('Time (ms)');fig.suptitle('LP20: aligned waveform, common scale');fig.tight_layout();fig.savefig(out/'waveforms.png',dpi=150);plt.close(fig)
    # Plot spectrum on a two-second active region, identical axes/color scale.
    pos=max(0,min(len(x)-96000,t0-48000));seg=slice(pos,pos+96000);f,tt,Z=stft(x[seg],48000,nperseg=1536,noverlap=1344,nfft=2048);mask=f<=3500;mx=20*np.log10(np.max(abs(Z))+1e-12);fig,ax=plt.subplots(4,1,figsize=(10,9),sharex=True,sharey=True,layout='constrained')
    for a,(name,y) in zip(ax,[('Reference',x),*ys.items()]):
        _,_,zz=stft(y[seg],48000,nperseg=1536,noverlap=1344,nfft=2048);im=a.pcolormesh(tt+pos/48000,f[mask],20*np.log10(abs(zz[mask])+1e-12),shading='auto',vmin=mx-65,vmax=mx);a.set_ylabel('Hz');a.set_title(name,loc='left',fontsize=10)
    ax[-1].set_xlabel('Time (s)');fig.colorbar(im,ax=ax,label='dB (common reference)');fig.savefig(out/'spectrogram.png',dpi=140);plt.close(fig)
    # Peak diagnostic at worst reference-aligned residual of recommended new profile.
    y=ys['v45 6k'];j=int(np.argmax(abs((y-x)[480:-480])))+480;lo=max(0,j-480);hi=min(len(x),j+480);t=np.arange(lo,hi)*1000/48000;direct=wavfile.read(out/'direct-pwm.wav')[1];dr,_,_=align(x,filt(direct.astype(float)/32768));fig,ax=plt.subplots(2,1,figsize=(10,5),sharex=True);ax[0].plot(t,x[lo:hi],label='Reference');ax[0].plot(t,y[lo:hi],label='v45 6k');ax[0].plot(t,dr[lo:hi],label='Direct PWM (no compression)',alpha=.7);ax[0].legend();ax[0].grid(alpha=.2);ax[1].plot(t,(y-x)[lo:hi],label='v45 error');ax[1].plot(t,(dr-x)[lo:hi],label='Direct PWM error');ax[1].legend();ax[1].grid(alpha=.2);ax[1].set_xlabel('Time (ms)');fig.tight_layout();fig.savefig(out/'peak-detail.png',dpi=150);plt.close(fig)
    # A/B reference, v44, v45 5.8, v45 6.0; 3 sec, with pauses, same global gain/delay.
    pos=max(0,min(len(x)-144000,t0-72000));a=[]
    for v in [x,ys['v44 Strict6'],ys['v45 5.8k'],ys['v45 6k']]:a.extend([v[pos:pos+144000],np.zeros(16800)])
    wavfile.write(out/'AB.wav',48000,np.clip(np.rint(np.concatenate(a)*32767),-32768,32767).astype(np.int16))
    (out/'book.bin').write_bytes(book);shutil.copy2(src/'dds.bin',out/'dds.bin')
for name,rows in [('comparison.csv',allrows),('selected.csv',selected)]:
    keys=list(dict.fromkeys(k for r in rows for k in r));f=open(ROOT/name,'w');w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows);f.close()
print('All selected WAVs regenerated exactly; report complete.')
