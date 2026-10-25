#!/usr/bin/env python3
"""Evaluate frozen unified-search settings on eight LPX-unseen cached speakers.

The cached speech corpus supplies source URLs, rights and original hashes.
No media are downloaded or committed. Keep output in an ignored build folder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import re
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from wav_lpc import load_wav
from wav_to_lpx4 import encode_segment
from optimize_q0 import optimize
from profile_avr import run as profile

SEARCH={'rounds':2,'lsf_trials':80,'beam_trials':256,'header_trials':40,
        'global_candidates':16,'global_states':256,'beam_width':4}


def run(corpus,output,report_path,avr_bin,runner,lib=None,wsl=None):
    corpus,output,report_path=map(Path,(corpus,output,report_path))
    output.mkdir(parents=True,exist_ok=True);report_path.parent.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    cases=[];sources=[]
    for source in manifest['sources']:
        if not re.fullmatch(r'[a-z][a-z0-9_]*',source['id']):raise ValueError('Unsafe source id')
        original=corpus/'originals'/(source['id']+'.ogg')
        if hashlib.sha256(original.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Source hash mismatch')
        pcm,info=load_wav(original);sources.append(source)
        for index,start in enumerate(source['starts']):
            cases.append((source['id']+'_'+chr(97+index),pcm[start*8000:start*8000+16000],
                'speech',{'source':source['id'],'start_seconds':start,'condition':'clean'}))
    lookup={key:pcm for key,pcm,_,_ in cases};rng=np.random.default_rng(20261025)
    for key,condition in [('ru_square_a','quiet'),('en_normcore_a','quiet'),
                          ('ru_russia_a','noise15'),('en_sense_a','noise15')]:
        x=lookup[key].astype(float)
        if condition=='quiet':x=x*10**(-24/20)
        else:x=x+rng.normal(0,np.sqrt(np.mean(x*x))/10**(15/20),len(x))
        cases.append((key+'_'+condition,np.clip(np.rint(x),-32768,32767).astype(np.int16),
            'speech',{'source_case':key,'condition':condition,'seed':20261025}))
    t=np.arange(16000)/8000
    for key,x in [('silence',np.zeros(16000)),('chirp',6000*np.sin(2*np.pi*(150*t+600*t*t))),
        ('transients',np.where((np.arange(16000)%1600)<80,rng.normal(0,6000,16000),0)),
        ('harmonic_music',4000*(np.sin(2*np.pi*220*t)+.5*np.sin(2*np.pi*330*t)+.25*np.sin(2*np.pi*880*t)))]:
        cases.append((key,np.clip(np.rint(x),-32768,32767).astype(np.int16),'music',{'synthetic':key,'seed':20261025}))
    report={'search':SEARCH,'protocol':'Frozen settings; 2s clips; eight LPX-unseen speakers, no gain/alignment fit; actual full-file byte cap; final full AVR cycle gate',
            'sources':sources,'cases':[]}
    with BatchSession('batch') as decoder:
        for key,ref,kind,provenance in cases:
            folder=output/key;folder.mkdir(exist_ok=True)
            sf.write(folder/'reference.wav',ref,8000,subtype='PCM_16')
            started=time.perf_counter()
            baseline,before,generation=encode_segment(ref,decoder,max_bytes=6000,kind=kind,
                lambdas=(0.,.001,.01,.1,1.,10.),canonical_zero=False)
            candidate,after,search=optimize(baseline,ref,decoder,kind=kind,**SEARCH)
            (folder/'baseline.l4hy').write_bytes(baseline);(folder/'candidate.l4hy').write_bytes(candidate)
            timings=[]
            for label in ('baseline','candidate'):
                if label=='candidate' and candidate==baseline:timings.append(timings[0]);continue
                timings.append(profile(folder/(label+'.l4hy'),folder/('avr-'+label),
                    avr_bin,runner,lib,wsl,enable_asm=True))
            a,b=timings
            accepted=(b['underruns']==0 and b['flash_bytes']<=32768 and
                b['mean_decode_wall_cycles']<=a['mean_decode_wall_cycles'] and
                b['decode_wall_cycles_max_160']<=a['decode_wall_cycles_max_160'])
            result,pcm=(candidate,after) if accepted else (baseline,before)
            (folder/'best.l4hy').write_bytes(result)
            sf.write(folder/'baseline.wav',before,8000,subtype='PCM_16')
            sf.write(folder/'best.wav',pcm,8000,subtype='PCM_16')
            item={'id':key,'kind':kind,'provenance':provenance,'samples':len(ref),
                'reference_sha256':hashlib.sha256(ref.astype('<i2').tobytes()).hexdigest(),
                'generation':generation,'search':search,'avr_before':a,'avr_candidate':b,
                'accepted_final':accepted,'bytes_before':len(baseline),'bytes_after':len(result),
                'elapsed_seconds':time.perf_counter()-started}
            report['cases'].append(item)
            report_path.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
            print(key,len(baseline),'->',len(result),'SER',search['before']['ser_db'],'->',
                search['after']['ser_db'] if accepted else search['before']['ser_db'],'timing accepted',accepted,flush=True)
    write_listening(report,output)
    return report


def write_listening(report,output):
    output=Path(output)
    # Listening assets deliberately keep labels and objective results out of HTML.
    keys={};rows=[]
    assets=output/'listening-assets';assets.mkdir(exist_ok=True)
    for index,item in enumerate(report['cases']):
        key=item['id'];flip=(hashlib.sha256((key+'20261025').encode()).digest()[0]&1)!=0
        labels=['best','baseline'] if flip else ['baseline','best'];keys[str(index+1)]=dict(zip(('A','B'),labels))
        for label,name in [('R','reference'),*zip(('A','B'),labels)]:
            (assets/f'{index+1:03d}-{label}.wav').write_bytes((output/key/(name+'.wav')).read_bytes())
        rows.append('<p>Case '+str(index+1)+' reference <audio controls src="listening-assets/'+f'{index+1:03d}-R.wav'+'"></audio></p>'+''.join(
            '<label>'+label+' <audio controls src="listening-assets/'+f'{index+1:03d}-{label}.wav'+'"></audio></label>' for label in ('A','B')))
    (output/'listening.html').write_text('<!doctype html><meta charset="utf-8"><title>LPX blinded A/B</title><h1>LPX blinded A/B</h1><p>Compare A and B at the same playback volume. Record preference before opening listening-key.json.</p>'+''.join(rows),encoding='utf-8')
    (output/'listening-key.json').write_bytes((json.dumps(keys,indent=2)+'\n').encode())
    (output/'attribution.json').write_bytes((json.dumps(report['sources'],ensure_ascii=False,indent=2)+'\n').encode())
    return output/'listening.html'


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','output','report'):ap.add_argument(name,type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args();run(a.corpus,a.output,a.report,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl)
