"""Bounded8/12/16 encoder development on frozen full references.

No decoder changes. A feasible rollback and PCM16 plus real PWM quality
floors are retained. New8 baselines are labelled separately from old data.
"""
import argparse,json,math,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from benchmark_standards import save,sha
from benchmark_multiseed import JointCache
from budget_search import search_budget
from joint_rate import encode_joint
from refine_speech8 import legacy_seed
from q0_model import decode_pcm16
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
from wav_to_lpx4 import quality

ROOT=Path(__file__).resolve().parents[1]
CONFIG={'rates':[8000,12000,16000],'samples':32000,'compact_features':24,
 'baseline8_lambdas':[.003,.03,.3,3.],'baseline8_refinements':4,'baseline8_beam':4,
 'quality_beam':8,'quality_refinements':2,'quality8_seeds':'rollback, enhanced12/16, available exact legacy transcodes of enhanced v5',
 'selection':'Full PCM16 and PWM SSE/STOI floors versus explicit rollback; SSE/bytes/hash.',
 'physical_board_measured':False,'human_listening_scores_collected':False}

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def revision():
    files=[p for p in sorted((ROOT/'src').iterdir()) if p.is_file()]
    names=('benchmark_profile_development','benchmark_standards','benchmark_multiseed',
        'budget_search','joint_rate','rate_distortion','q0_model','standard_metrics',
        'fast_lpx4','lpx4','wav_to_lpx4','wav_lpc','compact_format','speech_v4',
        'speech_compact','refine_speech8','batch_decoder','output_paths','l3av_parse',
        'rice_v3','rice_v4_reference','rice_v7')
    files.extend(ROOT/'tools'/(name+'.py') for name in names)
    return sha(b''.join(p.name.encode()+p.read_bytes() for p in files)+json.dumps(CONFIG,sort_keys=True).encode())

def point(blob,pcm,reference,kind,source):
    speech=kind=='speech';m=error_metrics(reference,pcm,speech)
    return (blob,pcm,{'source':source,'quality':m,'full_sse':int(m['error_energy'])})

def floor_ok(before,after):
    return after['error_energy']<=before['error_energy'] and (before['stoi'] is None or
        after['stoi'] is not None and after['stoi']>=before['stoi']-1e-12)

def choose(candidates,baseline,reference,kind,cap):
    """A smaller PCM error alone cannot hide a worse actual8-bit playback."""
    before=baseline[2]['quality'];pwm_before=error_metrics(reference,pwm_pcm16(baseline[1]),kind=='speech')
    eligible={sha(p[0]):p for p in [baseline,*candidates] if len(p[0])<=cap and floor_ok(before,p[2]['quality'])}
    if sha(baseline[0]) not in eligible:raise ValueError('Rollback is missing or over budget')
    rejected_pwm=0
    for p in sorted(eligible.values(),key=lambda p:(p[2]['full_sse'],len(p[0]),sha(p[0]))):
        pwm=error_metrics(reference,pwm_pcm16(p[1]),kind=='speech')
        if floor_ok(pwm_before,pwm):return p,{'eligible_pcm':len(eligible),'rejected_by_pwm':rejected_pwm,'pwm_baseline':pwm_before,'pwm_selected':pwm}
        rejected_pwm+=1
    raise AssertionError('The unchanged rollback must pass its own PWM floor')

def metadata(p,ref,kind):
    blob,pcm,meta=p
    return {'stream_sha256':sha(blob),'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),'pwm_sha256':sha(pwm_duties(pcm).tobytes()),
        'file_bytes':len(blob),'payload_bps':(len(blob)-20)*2,'file_bps':len(blob)*2,
        'quality':meta['quality'],'pwm_quality':error_metrics(ref,pwm_pcm16(pcm),kind=='speech'),
        'source':meta.get('source'),'lambda':meta.get('lambda'),'beam':meta.get('beam'),
        'native_model_exact':True,'native_pwm_exact':True}

def checked(blob,ref,decoder,kind,source,expected_pcm=None):
    if blob[4] not in (2,3) or int.from_bytes(blob[8:12],'little')!=len(ref):raise ValueError('Expected unchanged legacy format/count')
    pcm=decoder.decode_one_s16(blob,len(ref))
    if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('Native/model mismatch')
    if expected_pcm is not None and sha(pcm.astype('<i2').tobytes())!=expected_pcm:raise ValueError('Frozen PCM changed')
    if not np.array_equal(decoder.decode_one(blob,len(ref)),pwm_duties(pcm)):raise AssertionError('Native/PWM mismatch')
    return point(blob,pcm,ref,kind,source)

def lambda_grid(rate,center):
    default={8000:(.1,.3,1.),12000:(.01,.03,.1),16000:(.003,.01,.03)}[rate]
    center=float(center) if center is not None and center>0 else default[1]
    return tuple(sorted(set((*default,center/math.sqrt(2),center,center*math.sqrt(2)))))

def run(inputs,output,shard=0,shards=1,ids=None):
    if not 0<=shard<shards:raise ValueError('Invalid shard')
    inputs,output=Path(inputs),Path(output);manifest=load(inputs);rev=revision()
    if len({c['id'] for c in manifest['cases']})!=len(manifest['cases']):raise ValueError('Duplicate input IDs')
    # Every write belongs to output; none of the seed/reference files may be there.
    for c in manifest['cases']:
        for path in [Path(c['reference']),*[Path(r['path']) for r in c['rates']],*[Path(s['path']) for s in c.get('speech_seeds',[])]]:
            if output.resolve()==path.resolve() or output.resolve() in path.resolve().parents:raise ValueError('Output tree contains an input')
    selected_cases=[c for i,c in enumerate(manifest['cases']) if (ids is None or c['id'] in ids) and i%shards==shard]
    report={'revision':rev,'config':CONFIG,'shard':shard,'shards':shards,'cases':[],'decoder_modified':False}
    with BatchSession('batch',v3_features=24) as decoder:
        for c in selected_cases:
            started=time.perf_counter();folder=output/c['id'];folder.mkdir(parents=True,exist_ok=True)
            ref,sr=sf.read(c['reference'],dtype='int16')
            if sr!=8000 or ref.shape!=(32000,) or sha(ref.astype('<i2').tobytes())!=c['reference_sha256']:raise ValueError('Frozen reference changed')
            for record in [*c['rates'],*c.get('speech_seeds',[])]:
                if sha(Path(record['path']).read_bytes())!=record['stream_sha256']:raise ValueError('Frozen input changed')
            fingerprint=sha(json.dumps([rev,c],sort_keys=True).encode());done=folder/'complete.json'
            if done.exists():
                prior=load(done)
                if prior.get('fingerprint')==fingerprint:
                    for row in prior['rates']:
                        for stage in ('baseline','selected'):
                            path=folder/str(row['ceiling_bps'])/(stage+'.l4hy');b=path.read_bytes()
                            p=checked(b,ref,decoder,c['kind'],'cache',row[stage]['pcm16_sha256'])
                            if sha(b)!=row[stage]['stream_sha256']:raise ValueError('Completed stream changed')
                            wav,rate=sf.read(path.with_suffix('.wav'),dtype='int16')
                            if rate!=8000 or not np.array_equal(wav,p[1]):raise ValueError('Completed WAV changed')
                            fresh=metadata(p,ref,c['kind'])
                            for field in ('file_bytes','quality','pwm_quality','pwm_sha256'):
                                if fresh[field]!=row[stage][field]:raise ValueError('Completed quality metadata changed')
                        if not floor_ok(row['baseline']['quality'],row['selected']['quality']) or not floor_ok(row['baseline']['pwm_quality'],row['selected']['pwm_quality']):raise ValueError('Completed quality floor failed')
                    report['cases'].append(prior);save(output/f'part-{shard}.json',report);continue
            base={};centers={};old8=False
            for r in c['rates']:
                blob=Path(r['path']).read_bytes()
                if sha(blob)!=r['stream_sha256']:raise ValueError('Frozen seed changed')
                rate=r['ceiling_bps'];p=checked(blob,ref,decoder,c['kind'],'frozen_baseline',r.get('pcm16_sha256'))
                if len(blob)>20+rate//2:raise ValueError('Frozen baseline exceeds cap')
                base[rate]=p;centers[rate]=r.get('lambda');old8|=rate==8000
            if not all(r in base for r in (12000,16000)):raise ValueError('Both full-corpus12/16 baselines are required')
            cache=JointCache(folder/'candidates',ref,rev);extras=[]
            for s in c.get('speech_seeds',[]):
                blob=Path(s['path']).read_bytes()
                if sha(blob)!=s['stream_sha256']:raise ValueError('Frozen speech seed changed')
                legacy=legacy_seed(blob);extras.append(checked(legacy,ref,decoder,c['kind'],'enhanced_speech_seed'))
            if 8000 not in base:
                blob,pcm,search=search_budget([base[12000][0],base[16000][0]],ref,decoder,4020,c['kind'],
                    lambdas=CONFIG['baseline8_lambdas'],refinement_trials=CONFIG['baseline8_refinements'],encoder=cache,
                    encoder_options={'beam':CONFIG['baseline8_beam']})
                if blob is None:raise ValueError('Finite8k baseline search found no feasible rollback')
                base[8000]=checked(blob,ref,decoder,c['kind'],'new8_baseline');centers[8000]=search['selected'].get('lambda')
                save(folder/'baseline8-search.json',search)
            row={'id':c['id'],'kind':c['kind'],'group':c['group'],'reference_sha256':c['reference_sha256'],
                'samples':len(ref),'fingerprint':fingerprint,'baseline8_historically_measured':old8,'rates':[]}
            sf.write(folder/'original.wav',ref,8000,subtype='PCM_16')
            for rate in CONFIG['rates']:
                baseline=base[rate];cap=20+rate//2;candidates=[];search={'trials':0}
                seeds=[baseline[0]]
                if rate==8000:seeds.extend([base[12000][0],base[16000][0],*[p[0] for p in extras]])
                else:seeds.append(base[16000 if rate==12000 else 12000][0])
                if baseline[2]['full_sse']:
                    _,_,search=search_budget(seeds,ref,decoder,cap,c['kind'],lambdas=lambda_grid(rate,centers.get(rate)),
                        refinement_trials=CONFIG['quality_refinements'],encoder=cache,encoder_options={'beam':CONFIG['quality_beam']},
                        candidate_sink=lambda b,p,m:candidates.append((b,p,{**m,'quality':error_metrics(ref,p,c['kind']=='speech')})))
                chosen,gates=choose(candidates,baseline,ref,c['kind'],cap)
                verified=checked(chosen[0],ref,decoder,c['kind'],chosen[2].get('source','selected'))
                chosen=(verified[0],verified[1],{**chosen[2],**verified[2]})
                bm=metadata(baseline,ref,c['kind']);sm=metadata(chosen,ref,c['kind'])
                for stage,p in (('baseline',baseline),('selected',chosen)):
                    target=folder/str(rate);target.mkdir(parents=True,exist_ok=True)
                    (target/(stage+'.l4hy')).write_bytes(p[0]);sf.write(target/(stage+'.wav'),p[1],8000,subtype='PCM_16')
                if not floor_ok(bm['quality'],sm['quality']) or not floor_ok(bm['pwm_quality'],sm['pwm_quality']):raise AssertionError('Final full-reference quality floor failed')
                entry={'ceiling_bps':rate,'full_file_cap_bytes':cap,'baseline':bm,'selected':sm,
                    'changed':bm['stream_sha256']!=sm['stream_sha256'],'gates':gates,'trials':search['trials']}
                row['rates'].append(entry);save(folder/'partial.json',row);save(folder/str(rate)/'search.json',search)
                print(c['id'],rate,'selected',sm['file_bytes'],'SER',sm['quality']['ser_db'],'changed',entry['changed'],flush=True)
            row['seconds']=time.perf_counter()-started;row['cache']={'new_evaluations':cache.evaluations,'verified_hits':cache.hits}
            save(done,row);report['cases'].append(row);save(output/f'part-{shard}.json',report)
            print(c['id'],'complete',round(row['seconds'],2),'seconds',flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('inputs',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--shard',type=int,default=0);ap.add_argument('--shards',type=int,default=1);ap.add_argument('--ids',nargs='+')
    a=ap.parse_args();run(a.inputs,a.output,a.shard,a.shards,a.ids)
