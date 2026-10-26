"""Frozen encoder-only LPX low-rate ablations on the retained 27-case corpus.

All media/cache output must be ignored. Per-case caches verify reference,
source, configuration, encoded-stream and native PCM hashes. Independent
process shards have disjoint cases and report paths; no decoder changes.
"""
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,file_sha,sha
from rate_distortion import encode_rate
from budget_search import search_budget,spectrum_seeds
from joint_rate import encode_joint
from perceptual_rate import refine_perceptual
from lpx4 import decode
from standard_metrics import compare,pwm_duties

CONFIG={'rates':[12000,16000],
 'stage1_lambdas':[0.,.0003,.001,.003,.01,.03,.1,.3],
 'stage2_lambdas':[.001,.003,.01,.03,.1,.3,1.],
 'stage2_refinements':2,'spectrum_strides':[2,4],
 'stage3_lambdas':[.001,.003,.01,.03,.1], 'stage3_refinements':3,'beam':4,
 'stage4_trials':256,'stage4_windows':8,'gamma1':.9,'gamma2':.6,
 'stage4_peak_growth':.10,'stage4_max_ser_drop_db':3.,
 'tuning_sources':['ru_pushkin','ru_square','en_sense','en_portrait'],
 'compact_features':24,'protocol':'LOWRATE_QUALITY_PLAN_RU.md; fixed settings after tuning pilot; full 4s reference, no gain or delay fitting'}
STAGES=('real_bits','target_budget','joint','perceptual')
ROOT=Path(__file__).resolve().parents[1]


def revision():
    files=[*sorted((ROOT/'src').glob('*'))]
    names=('rate_distortion','budget_search','joint_rate','perceptual_rate','benchmark_lowrate',
           'q0_model','standard_metrics','fast_lpx4','lpx4','wav_to_lpx4','wav_lpc','compact_format')
    files.extend(ROOT/'tools'/(name+'.py') for name in names)
    return sha(b''.join(p.read_bytes() for p in files if p.is_file())+repr(CONFIG).encode())


def select_wave(items,cap,baseline=None):
    eligible=[p for p in items if len(p[0])<=cap]
    if baseline and len(baseline[0])<=cap:
        eligible.append(baseline);m=baseline[2]['metrics']['aligned_pcm16']
        eligible=[p for p in eligible if p[2]['metrics']['aligned_pcm16']['error_energy']<=m['error_energy'] and
            (m['stoi'] is None or p[2]['metrics']['aligned_pcm16']['stoi']>=m['stoi']-1e-12)]
    return min(eligible,key=lambda p:(p[2]['metrics']['aligned_pcm16']['error_energy'],len(p[0]),sha(p[0]))) if eligible else None


def run(baseline_root,corpus,output,report_path,ids=None,shard=0,shards=1):
    if not 0<=shard<shards:raise ValueError('Invalid shard')
    baseline_root,corpus,output,report_path=map(Path,(baseline_root,corpus,output,report_path))
    original=json.loads((baseline_root/'Codecs/LPX/research/q0-standards-2026-10-25/measurements.json').read_text(encoding='utf-8'))
    corpus_data=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'));source_revision=revision()
    report={'config':CONFIG,'revision':source_revision,'baseline_revision':original['lpx_revision'],
            'corpus_sha256':file_sha(corpus/'corpus.json'),'shard':shard,'shards':shards,
            'cases':[],'decoder_modified':False,'physical_hardware_measured':False,'human_scores_collected':False}
    selected=[c for c in corpus_data['cases'] if ids is None or c['id'] in ids]
    selected=[c for i,c in enumerate(selected) if i%shards==shard]
    with BatchSession('batch',v3_features=24) as decoder:
        for case in selected:
            key=case['id'];folder=output/key;folder.mkdir(parents=True,exist_ok=True)
            fingerprint=sha((source_revision+case['reference_sha256']+report['corpus_sha256']).encode())
            try:completed=json.loads((folder/'complete.json').read_text(encoding='utf-8'))
            except (FileNotFoundError,json.JSONDecodeError):completed=None
            if completed and completed.get('fingerprint')==fingerprint:
                for row in completed['rates']:
                    for stage in STAGES:
                        r=row[stage]
                        if r['status']=='ok' and file_sha(r['path'])!=r['stream_sha256']:raise ValueError('Completed result changed')
                report['cases'].append(completed);save(report_path,report);continue
            ref,rate=sf.read(corpus/key/'reference.wav',dtype='int16')
            if rate!=8000 or ref.shape!=(32000,) or sha(ref.astype('<i2').tobytes())!=case['reference_sha256']:raise ValueError('Reference changed')
            old=next(c for c in original['cases'] if c['id']==key);kind=case['kind']
            counters={'encoder_evaluations':0,'encoder_cache_hits':0};started=time.perf_counter()
            cache_folder=folder/'candidates';cache_folder.mkdir(exist_ok=True)
            memory={}
            def evaluate(seed,reference,decoder,lam,algorithm='real',**options):
                frames,_,_=decode(seed)
                input_key=(b''.join(frames)+seed[12:16]) if algorithm=='real' else seed
                signature=sha(input_key+ref.astype('<i2').tobytes()+repr((source_revision,algorithm,float(lam),options)).encode())
                if signature in memory:counters['encoder_cache_hits']+=1;return memory[signature]
                path=cache_folder/(signature+'.l4hy');meta=path.with_suffix('.json');pcm_path=path.with_suffix('.pcm16le')
                try:cached=json.loads(meta.read_text(encoding='utf-8'))
                except (FileNotFoundError,json.JSONDecodeError):cached=None
                if cached and path.exists() and pcm_path.exists() and file_sha(path)==cached['stream_sha256'] and file_sha(pcm_path)==cached['pcm16_sha256']:
                    result=path.read_bytes(),np.frombuffer(pcm_path.read_bytes(),dtype='<i2').copy(),cached
                    if result[1].shape!=(32000,):raise ValueError('Short cached PCM')
                    counters['encoder_cache_hits']+=1
                else:
                    function=encode_rate if algorithm=='real' else encode_joint
                    blob,pcm,r=function(seed,reference,decoder,lam=lam,**options)
                    path.write_bytes(blob);pcm_path.write_bytes(pcm.astype('<i2').tobytes())
                    r={**r,'path':str(path),'pcm16_sha256':sha(pcm.astype('<i2').tobytes())};save(meta,r)
                    result=blob,pcm,r;counters['encoder_evaluations']+=1
                memory[signature]=result;return result
            scored={}
            def score(blob,pcm,meta):
                digest=sha(blob)
                if digest not in scored:
                    metrics,_=compare(ref,pcm,kind=='speech',known_delay=0)
                    if not np.array_equal(pwm_duties(pcm),decoder.decode_one(blob,len(ref))):raise AssertionError('Native/common PWM mismatch')
                    scored[digest]={'status':'ok','file_bytes':len(blob),'audio_packet_bytes':len(blob)-20,
                        'stream_sha256':digest,'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),'metrics':metrics,
                        'native_model_pcm_exact':True,'native_pwm_exact':True,'selection':meta}
                return blob,pcm,scored[digest]
            def old_item(rate):
                r=next(x for x in old['rates'] if x['ceiling_bps']==rate)['LPX']
                if r['status']!='ok':return None
                blob=(baseline_root/r['path']).read_bytes()
                if sha(blob)!=r['stream_sha256']:raise ValueError('Baseline stream changed')
                return score(blob,decoder.decode_one_s16(blob,32000),{'source':'previous_baseline','ceiling_bps':rate})
            high=old_item(24000)
            if high is None:raise ValueError('Expected an admitted high-rate LPX seed')
            low=old_item(16000);dense=high[0]
            row={**case,'fingerprint':fingerprint,'split':'tuning' if case['provenance'].get('source') in CONFIG['tuning_sources'] else 'validation' if case['group']=='clean' else 'control',
                 'rates':[],'spectrum_audit':[],'searches':[]}
            # The first ablation isolates real-bit scoring with the unchanged
            # dense high-rate spectrum and no intentional zero-width blocks.
            real=[]
            for lam in CONFIG['stage1_lambdas']:
                b,p,r=evaluate(dense,ref,decoder,lam,allow_zero=False,compact_features=24,kind=kind)
                real.append(score(b,p,r))
            held,audit=spectrum_seeds(dense,CONFIG['spectrum_strides']);row['spectrum_audit']=audit
            pool=baseline_root/'build/lpx-standards/results'/key/'lpx-pool'
            pool_manifest=json.loads((pool/'pool.json').read_text(encoding='utf-8'))
            flat=next(c for c in pool_manifest['candidates'] if c['profile']=='flat')
            seeds=[dense,*held,(pool/flat['file']).read_bytes()]
            if low:seeds.append(low[0])
            for rate in CONFIG['rates']:
                cap=rate//2+20;old_at=old_item(rate);point={'ceiling_bps':rate,'cap_audio_bytes':rate//2,
                      'baseline':old_at[2] if old_at else {'status':'no_fit'}}
                winner=select_wave(real,cap,old_at)
                outputs={'real_bits':winner}
                b,p,r=search_budget(seeds,ref,decoder,cap,kind,lambdas=CONFIG['stage2_lambdas'],
                    refinement_trials=CONFIG['stage2_refinements'],encoder=evaluate)
                row['searches'].append({'stage':'target_budget','ceiling_bps':rate,**r})
                target=score(b,p,r['selected']) if b is not None else None
                target=select_wave([target] if target else [],cap,winner);outputs['target_budget']=target
                if target:
                    def joint(seed,reference,decoder,lam,**options):
                        return evaluate(seed,reference,decoder,lam,algorithm='joint',beam=CONFIG['beam'],**options)
                    b,p,r=search_budget([target[0]],ref,decoder,cap,kind,lambdas=CONFIG['stage3_lambdas'],
                        refinement_trials=CONFIG['stage3_refinements'],encoder=joint)
                    row['searches'].append({'stage':'joint','ceiling_bps':rate,**r})
                    joined=score(b,p,r['selected']);outputs['joint']=select_wave([joined],cap,target)
                    source=outputs['joint'];b,p,r=refine_perceptual(source[0],ref,decoder,
                        max_trials=CONFIG['stage4_trials'],max_windows=CONFIG['stage4_windows'],
                        gamma1=CONFIG['gamma1'],gamma2=CONFIG['gamma2'],kind=kind,
                        peak_growth=CONFIG['stage4_peak_growth'],max_ser_drop_db=CONFIG['stage4_max_ser_drop_db'])
                    outputs['perceptual']=score(b,p,r)
                    row['searches'].append({'stage':'perceptual','ceiling_bps':rate,**r})
                else:outputs.update(joint=None,perceptual=None)
                for stage,result in outputs.items():
                    if result:
                        b,p,r=result;path=folder/f'{rate}-{stage}.l4hy';path.write_bytes(b)
                        sf.write(path.with_suffix('.wav'),p,8000,subtype='PCM_16')
                        point[stage]={**r,'path':str(path)}
                    else:point[stage]={'status':'no_fit'}
                row['rates'].append(point);save(folder/'partial.json',row)
                print(key,rate,[(stage,point[stage]['status'],round(point[stage].get('metrics',{}).get('aligned_pcm16',{}).get('stoi') or 0,4)) for stage in STAGES],flush=True)
            row['counters']=counters;row['seconds']=time.perf_counter()-started
            save(folder/'complete.json',row);report['cases'].append(row);save(report_path,report)
            print(key,'complete',round(row['seconds'],1),'seconds',counters,flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline_root','corpus','output','report'):ap.add_argument(name,type=Path)
    ap.add_argument('--ids',nargs='+');ap.add_argument('--shard',type=int,default=0);ap.add_argument('--shards',type=int,default=1)
    a=ap.parse_args();run(a.baseline_root,a.corpus,a.output,a.report,a.ids,a.shard,a.shards)
