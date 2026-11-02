"""Compare exact Tiny models against time-aligned source spectrograms.

No playback-rate changes, trimming or level matching. The search changes only
decoder-native noise levels and, in a separate candidate grid, oscillator pitch.
All figures, WAVs and detailed candidates stay under ignored build storage.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'ATtiny13A/Sound/codec')]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'build/shared-speech/noise-refinement')
    p.add_argument('--avr-bin',type=Path,required=True)
    p.add_argument('--steps',type=int,default=800)
    p.add_argument('--seed',type=int,default=23121)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'build'):raise ValueError('Use ignored build storage')
    out.mkdir(parents=True,exist_ok=True)
    import numpy as np
    import soundfile as sf
    from scipy.ndimage import maximum_filter1d
    from scipy.signal import resample_poly,stft,correlate
    from pystoi import stoi
    from fixed_period import decode_fixed
    from tiny_period import pack_tiny
    from new_tiny_encoder import measure_code
    source=ROOT/'web-player/audio/lpx-bread/original.wav'
    original,rate=sf.read(source,dtype='float64');assert rate==8000
    reference=np.pad(resample_poly(original,15,16),(0,48));n=len(reference)
    f,t,z=stft(reference,fs=7500,nperseg=256,noverlap=192)
    target=abs(z);target_power=float(np.sum(target**2));floor=np.sqrt(np.mean(reference**2))*.004
    expanded=maximum_filter1d(target,3,axis=0)
    fine_target=abs(stft(reference,fs=7500,nperseg=1024,noverlap=896)[2])
    high=f>=1800;active=np.sqrt(np.mean(target**2,axis=0))>np.sqrt(np.mean(target**2))*.1
    block_rms=np.sqrt(np.mean(reference.reshape(-1,64)**2,axis=1));quiet=block_rms<np.sqrt(np.mean(reference**2))*.07
    code_cache={};candidates=[];models=[]
    sources=[ROOT/'ATtiny13A/Sound/research/shared-speech/bread-search-model.json']
    sources += [ROOT/f'build/shared-speech/tiny-fit-{mode}/{kind}-model.json'
                for mode in ('legacy','voice-priority') for kind in ('quality','fit')]
    seen=set()
    def assess(model,label):
        packed=pack_tiny(model);key=packed['flash_data']+packed['eeprom']
        if key in seen:return
        seen.add(key)
        words=packed['constants']['WAVE_BYTES']//16
        if words not in code_cache:code_cache[words]=measure_code(model,out/f'measure-{words}',a.avr_bin)['code_bytes']
        size=(code_cache[words]+len(packed['flash_data'])+1)&~1
        if size>1024:return
        pcm=(decode_fixed(model).astype(float)-128)/128
        mag=abs(stft(pcm,fs=7500,nperseg=256,noverlap=192)[2])
        excess=float(np.sum(np.maximum(mag[high]-expanded[high]-floor,0)**2)/target_power)
        missing=float(np.sum(np.maximum(target-maximum_filter1d(mag,3,axis=0)-floor,0)**2)/target_power)
        log=float(np.mean(abs(np.log(np.maximum(mag[:,active],floor))-np.log(np.maximum(target[:,active],floor)))))
        bands=float(np.linalg.norm(mag-target)/np.linalg.norm(target))
        intelligibility=float(stoi(reference,pcm,7500,extended=False))
        pause=float(np.mean(pcm.reshape(-1,64)[quiet]**2)) if quiet.any() else 0
        fine=abs(stft(pcm,fs=7500,nperseg=1024,noverlap=896)[2])
        fine_log=float(np.mean(abs(np.log(np.maximum(fine,floor))-np.log(np.maximum(fine_target,floor)))))
        score=.35*log+.15*fine_log+.2*bands+.9*np.sqrt(excess)+.2*np.sqrt(missing)
        item=dict(label=label,flashBytes=size,stoi=intelligibility,highBandExcess=excess,missingEnergy=missing,
                  rawLogSpectralError=log,fineLogSpectralError=fine_log,rawMagnitudeError=bands,quietRms=pause**.5,score=score)
        candidates.append(item);models.append(model)
    for path in sources:
        base=json.loads(path.read_text(encoding='utf-8'));label=path.parent.name+'/'+path.stem
        assess(base,label+'/unmodified')
        for factor in (1.,.875,.75,.625,.5,.375,.25,.125,0.):
            for pitch in (1.,.97,1.03):
                model=deepcopy(base)
                for index,frame in enumerate(model['frames']):
                    frame[2]=int(np.clip(round(frame[2]*factor),0,15))
                    frame[0]=int(np.clip(round(frame[0]*pitch),0,255))
                    if quiet[index]:frame[2]=0
                assess(model,f'{label}/noise={factor}/pitch={pitch}')
        # Preserve noisy consonants while suppressing residual on periodic frames.
        for voiced in (0.,.25,.5):
            model=deepcopy(base)
            for index,frame in enumerate(model['frames']):
                gain=(frame[1]>>4)&7
                factor=voiced if gain else 1.
                frame[2]=0 if quiet[index] else int(np.clip(round(frame[2]*factor),0,15))
            assess(model,f'{label}/voiced-noise={voiced}')
    eligible=[i for i,c in enumerate(candidates) if c['stoi']>=.67]
    if not eligible:raise ValueError('No candidate passes the intelligibility floor')
    winner=min(eligible,key=lambda i:candidates[i]['score'])
    initial=dict(candidates[winner]);floor_stoi=max(.67,initial['stoi']-.015)
    rng=np.random.default_rng(a.seed);accepted=0
    for step in range(a.steps):
        model=deepcopy(models[winner]);action=float(rng.random());frames=model['frames']
        if action<.45:
            words=pack_tiny(model)['constants']['WAVE_BYTES']//16
            word=int(rng.integers(words));at=int(rng.integers(32))
            model['codebook'][word][at]=int(np.clip(model['codebook'][word][at]+rng.choice([-1,1]),-7,7))
        else:
            start=int(rng.integers(len(frames)));length=int(rng.choice([1,2,3,4]))
            delta=int(rng.choice([-1,1]))
            for index in range(start,min(start+length,len(frames))):
                frame=frames[index]
                if action<.75:frame[2]=0 if quiet[index] else int(np.clip(frame[2]+delta,0,7))
                elif action<.95:frame[0]=int(np.clip(frame[0]+delta,0,255))
                else:
                    gains=[0,1,2,3,4,5,7];gain=(frame[1]>>4)&7
                    frame[1]=(frame[1]&143)|(gains[int(np.clip(gains.index(gain)+delta,0,len(gains)-1))]<<4)
        before=len(candidates);assess(model,f'spectral-step-{step}')
        if len(candidates)>before and candidates[-1]['stoi']>=floor_stoi and candidates[-1]['score']<candidates[winner]['score']:
            winner=len(candidates)-1;accepted+=1
    best=models[winner]
    incumbent=json.loads(sources[0].read_text(encoding='utf-8'))
    baseline=(decode_fixed(incumbent).astype(float)-128)/128
    selected=(decode_fixed(best).astype(float)-128)/128
    def envelope(x):return np.sqrt(np.mean(np.pad(x,(0,(-len(x))%64)).reshape(-1,64)**2,axis=1))
    correlation=correlate(envelope(reference)-envelope(reference).mean(),envelope(baseline)-envelope(baseline).mean(),mode='full')
    lag=int(np.argmax(correlation)-(len(envelope(baseline))-1))*64/7500
    receipt=dict(schema='tiny-noise-spectrogram-v1',sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        inputDurationSeconds=len(original)/rate,firmwareDurationSeconds=n/7500,samplePeriodCycles=1280,cpuHz=9600000,
        referenceSamples=18000,paddedSamples=n,incumbentEnvelopeLagSeconds=lag,timeCompression=False,levelMatching=False,
        selected=candidates[winner],baseline=next(item for item in candidates if item['label'].endswith('bread-search-model/unmodified')),
        initialDenoised=initial,refinementSteps=a.steps,acceptedSteps=accepted,seed=a.seed,
        candidateCount=len(candidates),stoiFloor=floor_stoi,
        candidates=sorted(candidates,key=lambda item:item['score'])[:12],
        scriptSha256NormalizedLF=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        sourceModels=[dict(file=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in sources])
    (out/'model.json').write_text(json.dumps(best,indent=2)+'\n',encoding='utf-8',newline='\n')
    receipt['modelSha256']=hashlib.sha256((out/'model.json').read_bytes()).hexdigest()
    (out/'report.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    (out/'all-candidates.json').write_text(json.dumps(candidates,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    for name,pcm in [('original',reference),('previous',baseline),('selected',selected)]:sf.write(out/(name+'.wav'),pcm,7500,subtype='PCM_16')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True,sharey=True,layout='constrained')
    for ax,(name,pcm) in zip(axes,[('Original',reference),('Previous firmware',baseline),('Selected quieter model',selected)]):
        freq,times,spectrum=stft(pcm,fs=7500,nperseg=256,noverlap=192)
        ax.pcolormesh(times,freq,20*np.log10(np.maximum(abs(spectrum),1e-5)),vmin=-75,vmax=-15,shading='auto',cmap='magma')
        ax.set_title(name);ax.set_ylabel('Hz');ax.set_ylim(0,3750)
    axes[-1].set_xlabel('Seconds — same time, frequency and dB scales; no level matching')
    fig.savefig(out/'spectrogram.png',dpi=150);plt.close(fig)
    print(json.dumps(dict(duration=receipt['firmwareDurationSeconds'],envelopeLag=lag,selected=candidates[winner],candidates=len(candidates))))


if __name__=='__main__':main()
