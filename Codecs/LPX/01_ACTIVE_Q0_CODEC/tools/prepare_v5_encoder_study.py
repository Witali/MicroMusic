"""Freeze strong v5 incumbents and exact 100/95/90 complete-chain budgets.

Private input paths, audio fingerprints and detailed metrics stay in build/.
Historical firmware costs are not accepted for the new encoder study.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession, ROOT
from benchmark_speech_flash import source_hashes
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
from refine_speech_compact import no_regression, quality
from select_speech_budget import evaluation_fingerprint, quality_source_fingerprint
from speech_compact import unpack, decode_model
from standard_metrics import pwm_duties


def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def cap(size, percent):
    if type(size) is not int or size < 22 or type(percent) is not int or percent not in (100,95,90):
        raise ValueError('Expected a complete v5 byte size and a 100/95/90 budget')
    return size * percent // 100


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def prepare(study, output):
    start=time.perf_counter();study=Path(study).resolve();output=checked_output(output)
    inputs={name:study/name for name in ('selection/results.json','firmware/all-costs.json',
                                        'corpus/strong-private.json','corpus/all-private.json')}
    for source in inputs.values():
        if output==source.parent or output in source.parents or source in output.parents:
            raise ValueError('Study outputs must be separate from immutable inputs')
    output.mkdir(parents=True,exist_ok=True)
    targets=[output/'manifest-private.json',output/'summary.json']
    protect_outputs(list(inputs.values())+[Path(__file__)],targets)
    if any(p.exists() for p in targets):
        raise ValueError('Use a fresh output directory; baseline evidence is immutable')
    source=source_hashes(ROOT/'src');qsource=quality_source_fingerprint()
    preparer_source=sha(Path(__file__).read_bytes())
    bindings={name:sha(path.read_bytes()) for name,path in inputs.items()}
    selected=load(inputs['selection/results.json']);costs=load(inputs['firmware/all-costs.json'])
    strong=load(inputs['corpus/strong-private.json']);corpus=load(inputs['corpus/all-private.json'])
    if selected.get('status')!='complete' or not costs.get('complete'):
        raise ValueError('Expected completed previous selection and stream inventory')
    if selected['costs_sha256']!=bindings['firmware/all-costs.json']:
        raise ValueError('Historical selection does not bind stream inventory')
    if selected['quality_source_fingerprint']!=qsource:
        raise ValueError('Recompute old metrics before comparing a changed metric implementation')
    groups={(g['id'],g['profile']):g for g in costs['groups']}
    metadata={c['id']:c for c in strong['cases']};private={c['id']:c for c in corpus['cases']}
    files={};decoded={};refs={};records=[];counts=collections.Counter();splits=collections.Counter()
    def verified_segments(entry):
        result=[];position=0
        for ordinal,segment in enumerate(entry['segments']):
            path=Path(segment['path']);blob=path.read_bytes();n,profile,*_=unpack(blob)
            if (sha(blob)!=segment['stream_sha256'] or len(blob)!=segment['file_bytes']
                    or segment['index']!=ordinal or segment['start']!=position or n!=segment['samples']):
                raise ValueError('Ordered source segments changed')
            files[str(path)]=sha(blob);position+=n
            result.append(dict(segment,profile=profile))
        return result
    with BatchSession('batch',v3_features=124,speech=True,speech_compact=True) as common, \
         BatchSession('batch',v3_features=124,speech=True,speech_compact=True,compact_only=True) as only:
        for ordinal,group in enumerate(sorted(selected['profiles'],key=lambda g:(g['id'],g['profile'])),1):
            key=(group['id'],group['profile']);inventory=groups[key];byid={r['id']:r for r in group['evaluated']}
            incumbent=byid[group['review']['selected_id']]
            for row in byid.values():
                if evaluation_fingerprint(row)!=row['evaluation_fingerprint']:
                    raise ValueError('Historical evaluation binding failed')
            eligible=[r for r in byid.values() if r['stream_bytes']<=incumbent['stream_bytes']
                      and no_regression(r['metrics'],incumbent['metrics'])]
            best=min(eligible,key=lambda r:(r['metrics']['pcm16']['error_energy'],
                     r['metrics']['pwm8']['error_energy'],r['stream_bytes'],r['id']))
            entry_by_hash={tuple(s['stream_sha256'] for s in e['segments']):e for e in inventory['entries']}
            segments=verified_segments(entry_by_hash[tuple(best['stream_sha256'])])
            reference=inventory['reference'];path=Path(reference['path']);raw=path.read_bytes()
            if sha(raw)!=reference['file_sha256']:
                raise ValueError('Original reference file changed')
            files[str(path)]=sha(raw)
            if group['id'] not in refs:
                ref,rate=sf.read(path,dtype='int16')
                if rate!=8000 or ref.ndim!=1 or len(ref)!=reference['samples']:
                    raise ValueError('Expected complete original mono PCM16/8kHz')
                if sha(ref.astype('<i2').tobytes())!=reference['pcm16_sha256']:
                    raise ValueError('Original PCM changed')
                refs[group['id']]=ref
            parts=[]
            for segment in segments:
                blob=Path(segment['path']).read_bytes();digest=sha(blob);n=segment['samples']
                if digest not in decoded:
                    pcm=decode_model(blob);pwm=pwm_duties(pcm)
                    for receiver in (common,only):
                        if not np.array_equal(receiver.decode_one_s16(blob,n),pcm) or not np.array_equal(receiver.decode_one(blob,n),pwm):
                            raise AssertionError('Frozen baseline native/model/PWM mismatch')
                    decoded[digest]=pcm;counts['native_pcm_pwm_comparisons']+=4
                parts.append(decoded[digest])
            pcm=np.concatenate(parts);ref=refs[group['id']]
            if len(pcm)!=len(ref) or sha(pcm.astype('<i2').tobytes())!=best['output_pcm16_sha256']:
                raise AssertionError('Frozen complete-chain output changed')
            measured=quality(ref,pcm)
            if measured!=best['metrics']:
                raise AssertionError('Fresh whole-reference baseline metrics changed')
            base_bytes=sum(s['file_bytes'] for s in segments);budgets=[]
            for percent in (100,95,90):
                limit=cap(base_bytes,percent)
                pool=[r for r in byid.values() if r['stream_bytes']<=limit]
                budgets.append({'percent':percent,'max_complete_stream_bytes':limit,
                    'prior_feasible_ids':[r['id'] for r in pool],
                    'prior_feasible_count':len(pool),'seed_exceeds_cap':base_bytes>limit})
                counts['budget_points']+=1;counts[f'prior_feasible_{percent}']+=bool(pool)
            meta=metadata[group['id']];old=private[meta['private_case_id']]
            if old['kind']!='speech' or old['samples']!=len(ref):
                raise ValueError('Historical speech cohort mapping changed')
            split=old['split']
            if split not in ('tuning','evaluation','additional'):
                raise ValueError('Unknown speech split')
            splits[split]+=1
            records.append({'id':f'speech-profile-{ordinal:03d}','private_case_id':group['id'],
                'profile':group['profile'],'reference':reference,'samples':len(ref),'split':split,
                'cohort':meta['cohort'],'language':meta['language'],'condition':meta['condition'],
                'baseline_id':best['id'],'baseline_bytes':base_bytes,'segments':segments,
                'baseline_metrics':measured,'baseline_pcm16_sha256':best['output_pcm16_sha256'],
                'baseline_pwm_sha256':best['output_pwm_sha256'],'budgets':budgets})
            counts['profile_groups']+=1;counts['segments']+=len(segments)
            if ordinal%10==0:print(json.dumps({'phase':'freeze-baseline','profiles':ordinal}),flush=True)
    if source_hashes(ROOT/'src')!=source or quality_source_fingerprint()!=qsource:
        raise ValueError('Decoder/model sources changed while freezing baseline')
    if sha(Path(__file__).read_bytes())!=preparer_source:
        raise ValueError('Baseline preparation source changed during the run')
    for name,path in inputs.items():
        if sha(path.read_bytes())!=bindings[name]:raise ValueError('Historical inputs changed')
    for name,digest in files.items():
        if sha(Path(name).read_bytes())!=digest:raise ValueError('Ordered stream source changed')
    if counts['profile_groups']!=98 or len(refs)!=49:
        raise ValueError('Expected the complete current49-case speech corpus in both profiles')
    manifest={'schema':'lpx-v5-encoder-quality-study-v1','source_sha256':source,
        'quality_source_fingerprint':qsource,'preparer_source_sha256':preparer_source,
        'input_manifests_sha256':bindings,'records':records}
    summary={'schema':'lpx-v5-encoder-quality-baseline-v1','status':'complete','baseline_commit':'22e50e01',
        'decoder_source_sha256':source,'quality_source_fingerprint':qsource,
        'preparer_source_sha256':preparer_source,'speech_cases':len(refs),
        'original_reference_samples':sum(len(x) for x in refs.values()),'counts':dict(counts),
        'profile_split_counts':dict(splits),'all_fresh_baseline_metrics_exact':True,
        'all_common_compact_model_pcm_pwm_exact':True,'historical_flash_reused':False,
        'budgets':'floor(achieved complete-chain bytes * percent /100), percent100/95/90',
        'elapsed_seconds':time.perf_counter()-start}
    save(targets[0],manifest);save(targets[1],summary);print(json.dumps(summary),flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.study,args.output)
