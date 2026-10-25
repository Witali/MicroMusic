#!/usr/bin/env python3
"""Frozen LPX/Opus/Vorbis/Speex comparison on common narrowband inputs.

Outputs include full-reference SER and worst sample deviation, with and
without delay compensation, before and after common 8-bit PWM conversion.
All audio/build files must be kept in ignored or external output directories.
"""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from compact_format import pack
from lossless_repack import optimize_scales,optimize_excitation
from optimize_q0 import optimize as optimize_quality
from q0_model import decode_pcm16
from standard_metrics import compare,error_metrics,pwm_duties,pwm_pcm16,ogg_accounting
from wav_lpc import load_wav
from wav_to_lpx4 import encode_segment,compact_zero_blocks

RATES=(8000,12000,16000,24000)
LAMBDAS=(0.,.001,.003,.01,.03,.1,1.,10.)
SEARCH={'rounds':1,'lsf_trials':80,'beam_trials':128,'header_trials':40,
        'global_candidates':8,'global_states':128,'beam_width':4}
STANDARD=('opus_audio','opus_voip','vorbis','speex_abr')


def sha(blob):return hashlib.sha256(blob).hexdigest()


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


@lru_cache(None)
def encoder_revision():return file_sha(shutil.which('ffmpeg'))


@lru_cache(None)
def lpx_revision():
    root=Path(__file__).resolve().parents[1]
    files=list((root/'src').glob('*.h'))+list((root/'src').glob('*.cpp'))+list((root/'src').glob('*.inc'))
    names=('wav_to_lpx4','wav_lpc','lpx4','fast_lpx4','q0_model','optimize_q0',
           'beam_excitation_pcm16','global_rate_pcm16','refine_lsf_pcm16','refine_excitation_pcm16',
           'tune_pcm16','lossless_repack','compact_format')
    files.extend(root/'tools'/(name+'.py') for name in names)
    return sha(b''.join(p.read_bytes() for p in sorted(files))+repr((LAMBDAS,SEARCH,'zero-scale-exact-compact24-v1')).encode())


def cached_json(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):return None


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.writing')
    temporary.write_bytes((json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
    temporary.replace(path)


def prepare(corpus,music_sources,output):
    corpus,output=Path(corpus),Path(output);output.mkdir(parents=True,exist_ok=True)
    original=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    report={'protocol':'new four-second windows at previous source starts +2s; mono PCM16 8kHz; no normalization',
            'sources':original['sources'],'cases':[]}
    arrays={}
    def add(key,pcm,kind,group,provenance):
        if not re.fullmatch(r'[a-z][a-z0-9_]*',key):raise ValueError('Unsafe case id')
        pcm=np.asarray(pcm,np.int16)
        if len(pcm)!=32000:raise ValueError('Corpus requires full 4-second clips: '+key)
        folder=output/key;folder.mkdir(exist_ok=True)
        sf.write(folder/'reference.wav',pcm,8000,subtype='PCM_16')
        sf.write(folder/'encoder-tail.wav',np.r_[pcm,np.zeros(640,np.int16)],8000,subtype='PCM_16')
        item={'id':key,'samples':len(pcm),'kind':kind,'group':group,'provenance':provenance,
              'reference_sha256':sha(pcm.astype('<i2').tobytes()),
              'reference_pwm_floor':error_metrics(pcm,pwm_pcm16(pcm),kind=='speech')}
        report['cases'].append(item);arrays[key]=pcm
    for source in original['sources']:
        if not re.fullmatch(r'[a-z][a-z0-9_]*',source['id']):raise ValueError('Unsafe source id')
        path=corpus/'originals'/(source['id']+'.ogg')
        if sha(path.read_bytes())!=source['sha256']:raise ValueError('Original source hash changed')
        pcm,_=load_wav(path)
        for i,start in enumerate(source['starts']):
            start=float(start)+2
            add(source['id']+'_'+chr(97+i)+'4',pcm[round(start*8000):round(start*8000)+32000],
                'speech','clean',{'source':source['id'],'start_seconds':start,'seconds':4})
    rng=np.random.default_rng(20261025)
    for key,condition in (('ru_square_a4','quiet'),('en_normcore_a4','quiet'),
                          ('ru_russia_a4','noise15'),('en_sense_a4','noise15')):
        pcm=arrays[key].astype(float)
        if condition=='quiet':pcm*=10**(-24/20)
        else:pcm+=rng.normal(0,np.sqrt(np.mean(pcm*pcm))/10**(15/20),len(pcm))
        add(key+'_'+condition,np.clip(np.rint(pcm),-32768,32767),'speech',condition,
            {'source_case':key,'condition':condition,'seed':20261025})
    for source in json.loads(Path(music_sources).read_text(encoding='utf-8')):
        path=Path(source['local'])
        if sha(path.read_bytes())!=source['sha256']:raise ValueError('Music hash changed')
        cmd=['ffmpeg','-nostdin','-v','error','-ss',str(source['start_seconds']),'-i',str(path),
             '-t','4','-ac','1','-ar','8000','-f','s16le','pipe:1']
        data=subprocess.run(cmd,check=True,capture_output=True).stdout
        add(source['id'],np.frombuffer(data,dtype='<i2'),'music','acoustic_music',
            {**source,'changes':'4-second excerpt; FFmpeg mono PCM16 8kHz; no normalization'})
        report['sources'].append(source)
    t=np.arange(32000)/8000
    stimuli={'harmonic_music':4000*(np.sin(2*np.pi*220*t)+.5*np.sin(2*np.pi*330*t)+.25*np.sin(2*np.pi*880*t)),
        'chirp':6000*np.sin(2*np.pi*(150*t+150*t*t)),
        'transients':np.where(np.arange(32000)%1600<80,rng.normal(0,6000,32000),0),
        'silence':np.zeros(32000)}
    for key,x in stimuli.items():add(key,np.clip(np.rint(x),-32768,32767),'music','synthetic',{'recipe':key,'seed':20261025})
    save(output/'corpus.json',report);return report


def compact(v2):
    v3,stats=pack(v2,24)
    return (v3 if len(v3)<len(v2) else v2),stats


def lpx_pool(reference,folder,decoder,kind):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'pool.json'
    fingerprint=sha(reference.astype('<i2').tobytes()+lpx_revision().encode()+kind.encode())
    data=cached_json(manifest)
    if data and data.get('fingerprint')==fingerprint:
        return data
    captured=[];started=time.perf_counter()
    _,_,generation=encode_segment(reference,decoder,max_bytes=65535,lambdas=LAMBDAS,kind=kind,
        canonical_zero=False,candidate_sink=lambda blob,r:captured.append((blob,r)))
    records=[]
    for index,(blob,metadata) in enumerate(captured):
        blob,zeros=compact_zero_blocks(blob,decoder)
        blob,scales=optimize_scales(blob)
        result,packing=compact(blob)
        path=folder/f'{index:03d}.l4hy';path.write_bytes(blob)
        records.append({'file':path.name,'v2_bytes':len(blob),'bytes':len(result),
            'audio_packet_bytes':len(result)-20,'version':result[4],
            'zero_blocks':zeros,'scales':scales,'packing':packing,**metadata})
        # Avoid a pre-repack metadata byte count overwriting actual sizes.
        records[-1].update(v2_bytes=len(blob),bytes=len(result),audio_packet_bytes=len(result)-20)
    data={'fingerprint':fingerprint,'reference_sha256':sha(reference.astype('<i2').tobytes()),'lambdas':LAMBDAS,
          'analysis':generation['analysis'],'candidates':records,'seconds':time.perf_counter()-started}
    save(manifest,data);return data


def select_lpx(pool,cap):
    available=[r for r in pool['candidates'] if r['audio_packet_bytes']<=cap]
    key=lambda r:(r['quality']['rmse'],r['bytes'],r['sha256'])
    legacy=[r for r in available if r['profile']=='legacy']
    if legacy:
        floor=min(legacy,key=key)['quality']['stoi']
        if floor is not None:available=[r for r in available if r['quality']['stoi']>=floor-1e-12]
    return min(available,key=key) if available else None


def encode_lpx(reference,folder,decoder,kind,cap):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cache=folder/'result.json'
    fingerprint=sha(reference.astype('<i2').tobytes()+repr((lpx_revision(),cap,kind)).encode())
    previous=cached_json(cache)
    if previous and previous.get('fingerprint')==fingerprint:return previous
    pool_folder=folder.parent/'lpx-pool';pool=lpx_pool(reference,pool_folder,decoder,kind)
    choice=select_lpx(pool,cap)
    if choice is None:
        result={'status':'no_fit','fingerprint':fingerprint,'cap_audio_bytes':cap,
                'minimum_candidate_audio_bytes':min(r['audio_packet_bytes'] for r in pool['candidates'])}
        save(cache,result);return result
    source=(pool_folder/choice['file']).read_bytes();baseline=source
    before=time.perf_counter()
    candidate,_,search=optimize_quality(source,reference,decoder,kind=kind,**SEARCH)
    candidate,_=compact_zero_blocks(candidate,decoder)
    candidate,scales=optimize_scales(candidate)
    candidate,exact=optimize_excitation(candidate,decoder)
    blob,packing=compact(candidate)
    original,_=compact(baseline)
    # Search preserves its original byte cap; compact metadata can change it.
    if len(blob)-20>cap:blob=original;candidate=baseline
    pcm=decoder.decode_one_s16(candidate,len(reference))
    if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('LPX model/native mismatch')
    # The main decoder includes all v3 bits, enabling direct native verification.
    if not np.array_equal(pcm,decoder.decode_one_s16(blob,len(reference))):raise AssertionError('LPX compact PCM mismatch')
    if not np.array_equal(pwm_duties(pcm),decoder.decode_one(blob,len(reference))):raise AssertionError('Common PWM differs from LPX')
    path=folder/'selected.l4hy';path.write_bytes(blob)
    sf.write(folder/'decoded.wav',pcm,8000,subtype='PCM_16')
    result={'status':'ok','fingerprint':fingerprint,'path':str(path),'cap_audio_bytes':cap,
        'file_bytes':len(blob),'audio_packet_bytes':len(blob)-20,'codec_setup_bytes':20,
        'comment_bytes':0,'container_overhead_bytes':0,'version':blob[4],
        'input_sha256':sha(reference.astype('<i2').tobytes()),'stream_sha256':sha(blob),
        'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),'native_model_pcm_exact':True,'native_pwm_exact':True,
        'selection':choice,'search':search,'exact_repack':exact,'scale_repack':scales,'packing':packing,
        'metrics':compare(reference,pcm,kind=='speech',known_delay=0)[0],
        'seconds':time.perf_counter()-before}
    save(cache,result);return result


def external_encoder(reference_path,folder,codec,bitrate):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{codec}-{bitrate}.ogg';record=path.with_suffix('.json')
    library={'opus_audio':'libopus','opus_voip':'libopus','vorbis':'libvorbis','speex_abr':'libspeex','speex_cbr':'libspeex'}[codec]
    options=[]
    if codec.startswith('opus'):
        options=['-application',codec.split('_')[1],'-compression_level','10','-frame_duration','20','-vbr','on']
    elif codec.startswith('speex'):
        options=['-compression_level','10','-abr','1' if codec=='speex_abr' else '0','-vad','0','-dtx','0','-frames_per_packet','1']
    cmd=['ffmpeg','-nostdin','-y','-v','error','-i',str(reference_path),'-map_metadata','-1',
         '-ac','1','-ar','8000','-c:a',library,'-b:a',str(bitrate),*options,'-fflags','+bitexact',str(path)]
    fingerprint=sha((encoder_revision()+file_sha(reference_path)+repr(cmd[:-1])).encode())
    previous=cached_json(record)
    if previous and previous.get('fingerprint')==fingerprint:
        if previous['status']!='ok' or (path.exists() and file_sha(path)==previous['stream_sha256']):return previous
    started=time.perf_counter();p=subprocess.run(cmd,capture_output=True)
    result={'fingerprint':fingerprint,'requested_bitrate':bitrate,'command':cmd,'seconds':time.perf_counter()-started}
    if p.returncode:result.update(status='encoder_error',error=p.stderr.decode(errors='replace')[-800:])
    else:result.update(status='ok',path=str(path),stream_sha256=sha(path.read_bytes()),**ogg_accounting(path.read_bytes()))
    save(record,result);return result


def fit_external(reference_path,folder,codec,cap,field='audio_packet_bytes'):
    # Fixed domains avoid treating Vorbis's high-rate setup rejection as a
    # request to search still higher unsupported narrowband bitrates.
    lo,hi=(6000,64000) if codec.startswith('opus') else (8000,40000) if codec=='vorbis' else (2000,32000)
    best=None;trials=[]
    for _ in range(16):
        if lo>hi:break
        bitrate=(lo+hi)//2;r=external_encoder(reference_path,folder,codec,bitrate)
        trials.append({'requested_bitrate':bitrate,'status':r['status'],
                       'bytes':r.get(field),'error':r.get('error')})
        if r['status']!='ok':lo=bitrate+1;continue
        size=r[field]
        if size<=cap:
            if best is None or size>best[field]:best=r
            lo=bitrate+1
            if cap-size<=max(1,cap//200):break
        else:hi=bitrate-1
    if best is None:return {'status':'no_fit','cap_bytes':cap,'budget_field':field,'trials':trials}
    return {**best,'cap_bytes':cap,'budget_field':field,'shortfall_bytes':cap-best[field],
            'shortfall_fraction':(cap-best[field])/cap,'trials':trials}


def score_external(reference,item,kind,output):
    if item['status']!='ok':return item
    cmd=['ffmpeg','-nostdin','-v','error','-i',item['path'],'-ac','1','-ar','8000','-f','s16le','pipe:1']
    decoded=subprocess.run(cmd,check=True,capture_output=True)
    pcm=np.frombuffer(decoded.stdout,dtype='<i2')
    metrics,aligned=compare(reference,pcm,kind=='speech')
    sf.write(output,aligned,8000,subtype='PCM_16')
    return {**item,'metrics':metrics,'decoded_samples':len(pcm),
            'aligned_pcm16_sha256':sha(aligned.astype('<i2').tobytes()),
            'decoder_command':cmd,'decoder_warnings':decoded.stderr.decode(errors='replace')}


def run(corpus,output,report_path,ids=None,shard=0,shards=1):
    if not 0<=shard<shards:raise ValueError('Invalid shard')
    corpus,output,report_path=Path(corpus),Path(output),Path(report_path)
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    selected=[c for c in manifest['cases'] if ids is None or c['id'] in ids]
    selected=[c for i,c in enumerate(selected) if i%shards==shard]
    report={'protocol':'PROTOCOL.md; common mono PCM16 8kHz; actual audio-packet ceilings and separate complete-file ceilings',
            'rates':RATES,'lambdas':LAMBDAS,'search':SEARCH,'sources':manifest['sources'],
            'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            'ffmpeg_sha256':encoder_revision(),'lpx_revision':lpx_revision(),'shard':shard,'shards':shards,
            'cases':[],'physical_hardware_measured':False,'subjective_listening_scores_collected':False}
    with BatchSession('batch',v3_features=124) as decoder:
        for case in selected:
            key=case['id'];folder=output/key;folder.mkdir(parents=True,exist_ok=True)
            reference=load_wav(corpus/key/'reference.wav')[0]
            if sha(reference.astype('<i2').tobytes())!=case['reference_sha256']:raise ValueError('Reference hash changed')
            fingerprint=sha((case['reference_sha256']+file_sha(__file__)+lpx_revision()+encoder_revision()).encode())
            completed=cached_json(folder/'complete.json')
            if completed and completed.get('fingerprint')==fingerprint:
                report['cases'].append(completed);save(report_path,report);continue
            item={**case,'rates':[],'matched_file':{},'speex_cbr_points':[]}
            item['fingerprint']=fingerprint
            for rate in RATES:
                cap=int(rate*len(reference)/8000/8)
                rate_folder=folder/str(rate);rate_folder.mkdir(exist_ok=True)
                lpx=encode_lpx(reference,rate_folder,decoder,case['kind'],cap)
                row={'ceiling_bps':rate,'cap_audio_bytes':cap,'LPX':lpx}
                for codec in STANDARD:
                    fit=fit_external(corpus/key/'encoder-tail.wav',folder/'external',codec,cap)
                    row[codec]=score_external(reference,fit,case['kind'],rate_folder/(codec+'.wav'))
                item['rates'].append(row)
                save(rate_folder/'comparison.json',row)
                print(key,rate,'LPX',lpx['status'],
                      'SER',round(lpx['metrics']['aligned_pcm16']['ser_db'],2) if lpx['status']=='ok' and lpx['metrics']['aligned_pcm16']['ser_db'] is not None else None,
                      'standards',[row[c]['status'] for c in STANDARD],flush=True)
                report['cases']=[c for c in report['cases'] if c['id']!=key]+[item];save(report_path,report)
            # Genuine CBR operating points, not an assumed continuous Speex rate.
            for bitrate in (8000,11000,15000,18200,24600):
                encoded=external_encoder(corpus/key/'encoder-tail.wav',folder/'external','speex_cbr',bitrate)
                item['speex_cbr_points'].append(score_external(reference,encoded,case['kind'],folder/f'speex-cbr-{bitrate}.wav'))
            high=item['rates'][-1]['LPX']
            if high['status']=='ok':
                for codec in STANDARD:
                    fit=fit_external(corpus/key/'encoder-tail.wav',folder/'external',codec,high['file_bytes'],'file_bytes')
                    item['matched_file'][codec]=score_external(reference,fit,case['kind'],folder/(codec+'-matched-file.wav'))
            report['cases']=[c for c in report['cases'] if c['id']!=key]+[item];save(report_path,report)
            save(folder/'complete.json',item)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare');p.add_argument('corpus',type=Path);p.add_argument('music_sources',type=Path);p.add_argument('output',type=Path)
    p=sub.add_parser('run');p.add_argument('corpus',type=Path);p.add_argument('output',type=Path);p.add_argument('report',type=Path)
    p.add_argument('--ids',nargs='+')
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    a=ap.parse_args()
    if a.mode=='prepare':prepare(a.corpus,a.music_sources,a.output)
    else:run(a.corpus,a.output,a.report,a.ids,a.shard,a.shards)
