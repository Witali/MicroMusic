"""Frozen full-corpus retry of the listening-guided two-seed LPX search.

Compare both the original audio ceiling and the original actual file cap.
All codec/decoder code is reused. Persistent caches verify encoded and PCM
bytes; process shards have disjoint cases. Generated media stays ignored.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,sha,file_sha
from budget_search import search_budget
from joint_rate import encode_joint
from wav_to_lpx4 import quality
from standard_metrics import compare,pwm_duties
from lpx4 import decode

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'rates':[12000,16000],'seed_rates':[12000,16000],
        'lambdas':[.003,.01,.03,.1],'refinement_trials':10,'beam':4,'compact_features':24,
        'controls':['equal_ceiling','old_file_cap'],'baseline_stage':'joint',
        'stimulus_case':'ru_pushkin_a4','reference_samples':32000,
        'selection':'Full SSE and speech STOI no worse than the corresponding original joint; then SSE/bytes/hash.',
        'protocol':'q0-multiseed-2026-10-25/PROTOCOL.md'}
STAGES=('enhanced','size_matched')


def revision():
    names=('benchmark_multiseed','budget_search','joint_rate','rate_distortion','q0_model',
           'standard_metrics','fast_lpx4','lpx4','wav_to_lpx4','wav_lpc','compact_format')
    files=[p for p in sorted((ROOT/'src').iterdir()) if p.is_file()]
    files.extend(ROOT/'tools'/(name+'.py') for name in names)
    return sha(b''.join(p.read_bytes() for p in files)+repr(CONFIG).encode())


class JointCache:
    def __init__(self,folder,reference,source_revision,encoder=encode_joint):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.reference=np.asarray(reference,np.int16);self.ref_sha=sha(self.reference.astype('<i2').tobytes())
        self.revision=source_revision;self.encoder=encoder;self.memory={};self.evaluations=0;self.hits=0

    def __call__(self,seed,reference,decoder,lam,**options):
        if sha(np.asarray(reference,dtype='<i2').tobytes())!=self.ref_sha:raise ValueError('Cache reference changed')
        key=sha(seed+self.ref_sha.encode()+self.revision.encode()+repr((float(lam),sorted(options.items()))).encode())
        if key in self.memory:self.hits+=1;return self.memory[key]
        blob_path=self.folder/(key+'.l4hy');pcm_path=blob_path.with_suffix('.pcm16le');meta_path=blob_path.with_suffix('.json')
        try:
            r=json.loads(meta_path.read_text(encoding='utf-8'));raw=blob_path.read_bytes();data=pcm_path.read_bytes()
            valid=(r['fingerprint']==key and sha(raw)==r['stream_sha256'] and sha(data)==r['pcm16_sha256'] and len(data)==len(self.reference)*2)
        except (OSError,ValueError,KeyError):valid=False
        if valid:
            result=raw,np.frombuffer(data,dtype='<i2').copy(),r;self.hits+=1
        else:
            raw,pcm,r=self.encoder(seed,reference,decoder,lam=lam,**options)
            pcm=np.asarray(pcm,dtype='<i2')
            if pcm.shape!=self.reference.shape:raise AssertionError('Encoder returned a partial reference')
            blob_path.write_bytes(raw);pcm_path.write_bytes(pcm.tobytes())
            r={**r,'fingerprint':key,'stream_sha256':sha(raw),'pcm16_sha256':sha(pcm.tobytes()),'path':str(blob_path)}
            save(meta_path,r);result=raw,pcm,r;self.evaluations+=1
        self.memory[key]=result;return result


def choose(candidates,baseline,max_bytes):
    """Explicit target baseline floor, independent of the other feasible seed."""
    floor=baseline[2]['quality']['stoi'];limit=baseline[2]['full_sse']
    eligible=[p for p in [baseline,*candidates] if len(p[0])<=max_bytes and p[2]['full_sse']<=limit and
              (floor is None or p[2]['quality']['stoi']>=floor-1e-12)]
    if not eligible:raise ValueError('The required feasible rollback is missing')
    return min(eligible,key=lambda p:(p[2]['full_sse'],len(p[0]),sha(p[0])))


def spectral_signature(blob):
    return sha(blob[12:16]+b''.join(decode(blob)[0]))


def run(baseline_root,corpus,output,report_path,ids=None,shard=0,shards=1):
    if not 0<=shard<shards:raise ValueError('Invalid shard')
    baseline_root,corpus,output,report_path=map(Path,(baseline_root,corpus,output,report_path))
    baseline_path=baseline_root/'Codecs/LPX/research/q0-lowrate-2026-10-25/measurements.json'
    old=json.loads(baseline_path.read_text(encoding='utf-8'));manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    source_revision=revision();base_sha=file_sha(baseline_path);corpus_sha=file_sha(corpus/'corpus.json')
    report={'config':CONFIG,'revision':source_revision,'baseline_sha256':base_sha,'corpus_sha256':corpus_sha,
            'shard':shard,'shards':shards,'cases':[],'decoder_modified':False,'physical_hardware_measured':False}
    cases=[c for c in manifest['cases'] if ids is None or c['id'] in ids]
    cases=[c for i,c in enumerate(cases) if i%shards==shard]
    with BatchSession('batch',v3_features=24) as decoder:
        for c in cases:
            name=c['id'];folder=output/name;folder.mkdir(parents=True,exist_ok=True)
            fingerprint=sha((source_revision+base_sha+corpus_sha+c['reference_sha256']).encode())
            try:completed=json.loads((folder/'complete.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):completed=None
            if completed and completed.get('fingerprint')==fingerprint:
                for row in completed['rates']:
                    for stage in STAGES:
                        r=row[stage]
                        if file_sha(r['path'])!=r['stream_sha256']:raise ValueError('Completed stream changed')
                        pcm,rate=sf.read(Path(r['path']).with_suffix('.wav'),dtype='int16')
                        if rate!=8000 or pcm.shape!=(32000,) or sha(pcm.astype('<i2').tobytes())!=r['pcm16_sha256']:raise ValueError('Completed PCM changed')
                report['cases'].append(completed);save(report_path,report);continue
            ref,rate=sf.read(corpus/name/'reference.wav',dtype='int16')
            if rate!=8000 or ref.shape!=(32000,) or sha(ref.astype('<i2').tobytes())!=c['reference_sha256']:raise ValueError('Reference changed')
            original=next(p for p in old['cases'] if p['id']==name);kind=c['kind'];baselines={};scored={}
            def score(blob,pcm,meta):
                digest=sha(blob)
                if digest not in scored:
                    metrics,_=compare(ref,pcm,kind=='speech',known_delay=0)
                    if not np.array_equal(pwm_duties(pcm),decoder.decode_one(blob,32000)):raise AssertionError('Native/common PWM mismatch')
                    scored[digest]={'status':'ok','stream_sha256':digest,'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),
                        'file_bytes':len(blob),'audio_packet_bytes':len(blob)-20,'metrics':metrics,'selection':meta,
                        'spectral_signature':spectral_signature(blob),'native_model_pcm_exact':True,'native_pwm_exact':True}
                return scored[digest]
            seeds=[];seed_info=[]
            for rate in CONFIG['seed_rates']:
                previous=next(r for r in original['rates'] if r['ceiling_bps']==rate)['joint']
                if previous['status']!='ok':raise ValueError('Original joint baseline missing')
                path=baseline_root/previous['path'];blob=path.read_bytes()
                if sha(blob)!=previous['stream_sha256']:raise ValueError('Original stream changed')
                pcm=decoder.decode_one_s16(blob,32000)
                if pcm is None or sha(pcm.astype('<i2').tobytes())!=previous['pcm16_sha256']:raise AssertionError('Original native PCM changed')
                error=ref.astype(np.int64)-pcm.astype(np.int64)
                meta={'source':'target_baseline','seed_rate':rate,'quality':quality(ref,pcm,kind),
                      'full_sse':int(np.dot(error,error)),'stream_sha256':sha(blob)}
                baselines[rate]=(blob,pcm,meta);seeds.append(blob)
                seed_info.append({'ceiling_bps':rate,'file_bytes':len(blob),'stream_sha256':sha(blob),'path':str(path)})
            cache=JointCache(folder/'candidates',ref,source_revision);started=time.perf_counter();budgets={}
            row={**c,'fingerprint':fingerprint,'split':original['split'],'seed_info':seed_info,'rates':[],'searches':[]}
            for rate in CONFIG['rates']:
                baseline=baselines[rate];base=score(*baseline);point={'ceiling_bps':rate,'cap_audio_bytes':rate//2,
                    'baseline':base,'old_file_cap_bytes':len(baseline[0])}
                for stage,cap in [('enhanced',rate//2+20),('size_matched',len(baseline[0]))]:
                    if cap not in budgets:
                        candidates=[]
                        b,p,s=search_budget(seeds,ref,decoder,cap,kind,lambdas=CONFIG['lambdas'],
                            refinement_trials=CONFIG['refinement_trials'],encoder=cache,
                            encoder_options={'beam':CONFIG['beam']},candidate_sink=lambda b,p,r:candidates.append((b,p,r)))
                        budgets[cap]=candidates,s
                    candidates,s=budgets[cap];chosen=choose(candidates,baseline,cap);blob,pcm,meta=chosen
                    item=score(blob,pcm,meta);path=folder/f'{rate}-{stage}.l4hy';path.write_bytes(blob)
                    sf.write(path.with_suffix('.wav'),pcm,8000,subtype='PCM_16')
                    feasible=[p for p in candidates if len(p[0])<=cap]
                    raw=min(feasible,key=lambda p:(p[2]['full_sse'],len(p[0]),sha(p[0])))
                    point[stage]={**item,'path':str(path),'cap_file_bytes':cap,
                        'changed':sha(blob)!=sha(baseline[0]),'spectrum_changed':item['spectral_signature']!=base['spectral_signature'],
                        'raw_best':{k:raw[2].get(k) for k in ('stream_sha256','full_sse','quality','file_bytes','source','seed_index','lambda')},
                        'raw_best_rejected_by_stoi':kind=='speech' and raw[2]['quality']['stoi']<baseline[2]['quality']['stoi']-1e-12}
                    row['searches'].append({'stage':stage,'ceiling_bps':rate,**s})
                    print(name,rate,stage,len(blob),round(item['metrics']['aligned_pcm16']['ser_db'] or 0,3),round(item['metrics']['aligned_pcm16']['stoi'] or 0,4),flush=True)
                row['rates'].append(point);save(folder/'partial.json',row)
            row['seconds']=time.perf_counter()-started;row['cache']={'new_evaluations':cache.evaluations,'verified_hits':cache.hits}
            save(folder/'complete.json',row);report['cases'].append(row);save(report_path,report)
            print(name,'complete',round(row['seconds'],1),row['cache'],flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline_root','corpus','output','report'):ap.add_argument(name,type=Path)
    ap.add_argument('--ids',nargs='+');ap.add_argument('--shard',type=int,default=0);ap.add_argument('--shards',type=int,default=1)
    a=ap.parse_args();run(a.baseline_root,a.corpus,a.output,a.report,a.ids,a.shard,a.shards)
