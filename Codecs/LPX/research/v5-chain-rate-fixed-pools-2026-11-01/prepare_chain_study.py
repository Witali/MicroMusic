"""Metadata-only closure of the original retained V1 pools; no DP or decoding."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import traceback

from chain_study_policy import (PRODUCER,V1_PRODUCER,restrict_pool,validate_jobs,V1)
from chain_study_runtime import (ROOT,PREFIX,Inputs,SUPPORT,sha,save,sources,fresh_output,
                                verify_v1_bridge,timed,elapsed,runtime_identity)


def prepare(args):
    began=timed();inputs=Inputs();recipe=sources()
    closed=inputs.json(args.v1_export/'binding-private.json')
    summary=inputs.json(args.v1_export/'summary.json')
    if (closed['status']!='PASS' or closed['production_source_commit']!=V1_PRODUCER
            or not closed['zero_search_refit_metric_decode_native_build_calls']
            or (summary['status'],summary['pilot_contexts'],summary['arm_records'],summary['corpus_helper_calls'],summary['cap_views'])
                !=('PASS',12,60,100,180)):
        raise ValueError('The completed V1 saved-decision audit changed')
    for name,digest in closed['input_files_sha256'].items():inputs.read(name,digest)
    old_pins=closed['input_files_sha256']
    def old_read(path):
        key=str(Path(path).resolve())
        if key not in old_pins:raise ValueError('A V1 artifact is outside its closed projector input graph')
        return inputs.read(path,old_pins[key])
    def old_json(path):return json.loads(old_read(path))
    def old_stream(meta):
        raw=old_read(meta['path'])
        if sha(raw)!=meta['stream_sha256'] or len(raw)!=meta['file_bytes']:
            raise ValueError('Actual V1 stream binding changed')
        return raw
    old_research=args.v1_root/'Codecs/LPX/research'
    for name,digest in closed['projection_sources'].items():inputs.read(old_research/name,digest)
    inventory=SUPPORT.bind_production(args.source_root,PRODUCER)
    baselines_path=Path(closed['baselines_path']);raw=old_read(baselines_path);baselines=json.loads(raw)
    marker=old_json(baselines_path.parent/'complete-private.json')
    if marker['status']!='complete' or marker['binding_sha256']!=sha(raw):
        raise ValueError('The original no-search baseline preparation is not closed')
    bases={b['id']:b for b in baselines['baselines']};bindings=[];jobs=[]
    for shard_path in closed['shard_paths']:
        shard=Path(shard_path);binding=old_json(shard/'binding-private.json')
        if shard.name!='pilot-v1-p%d'%binding['profile']:raise ValueError('Only the immutable V1 shards may supply pools')
        attempt=old_json(shard/'attempt-private.json');terminal=old_json(shard/'summary.json')
        rows=old_json(shard/'results-private.json')
        if (attempt['status']!='complete' or terminal['status']!='PASS' or terminal['helper_calls']!=50
                or terminal['arm_records']!=30 or attempt['forbidden_fit_or_build_attempts']
                or any(e['status']!='complete' for e in attempt['helper_calls'])):
            raise ValueError('A V1 worker is incomplete or contains an unclosed helper')
        for name,digest in binding['research_sources'].items():inputs.read(old_research/name,digest)
        if binding['native_bridge']['old_native_cases_sha256']!=sha(inputs.read(args.native_cases)):
            raise ValueError('The supplied old native cases are not V1 native cases')
        bindings.append(binding)
        for row in rows:
            if row!=old_json(shard/'arms'/('job-%03d'%row['id'])/'result-private.json'):
                raise ValueError('A saved individual arm differs from its terminal row')
            base=bases[row['baseline_id']]
            baseline=tuple(old_stream(meta) for meta in base['segments'])
            if (row['baseline_bytes']!=sum(map(len,baseline)) or row['baseline_bytes']!=base['stream_bytes']
                    or row['local_byte_cap']!=min(row['baseline_bytes'],65535) or row['profile']!=base['profile']):
                raise ValueError('The actual original B/profile/local generation cap changed')
            if len(row['whole_chains'])!=len(row['whole_rows']):raise ValueError('A protected whole row is missing')
            known={sha(blob):meta for blob,meta in zip(baseline,base['segments'])}
            original_parts=[]
            for chain,value in zip(row['whole_chains'],row['whole_rows']):
                parts=tuple(old_stream(meta) for meta in chain['segments'])
                if sum(map(len,parts))!=value['stream_bytes'] or chain['id']!=value['id']:
                    raise ValueError('A protected original chain changed')
                original_parts.append(parts)
                for blob,meta in zip(parts,chain['segments']):known[sha(blob)]=meta
            if original_parts[0]!=baseline:raise ValueError('The immutable original baseline changed')
            restricted=[];locals=[]
            for local in row['locals']:
                index=local['index'];folder=shard/'arms'/('job-%03d'%row['id'])/('reset-%03d'%index)
                if local!=old_json(folder/'endpoint-private.json') or old_json(folder/'attempt-private.json')['status']!='complete':
                    raise ValueError('An exact local completion receipt differs')
                for order,meta in enumerate(local['captured_streams']):
                    blob=old_stream(meta)
                    if meta['callback_order']!=order:raise ValueError('Saved callback order changed')
                    known[sha(blob)]=meta
                pool=[]
                for position,meta in enumerate(local['pool']):
                    saved=known.get(meta['stream_sha256'])
                    if saved is None or meta['id']!=position:raise ValueError('A stable saved pool option disappeared')
                    blob=old_stream(saved)
                    if len(blob)!=meta['file_bytes']:raise ValueError('Actual saved pool rate changed')
                    pool.append(dict(id=position,blob=blob,sse=meta['sse']))
                cut=restrict_pool(pool,local['frontier_ids'],baseline[index],local['selected_id'],local['raw_id'],row['local_byte_cap'])
                locals.append(dict(index=index,selected=cut['selected'],raw=cut['raw'],frontier=cut['frontier']))
                restricted.append(dict(index=index,baseline_id=cut['baseline_id'],rows=[
                    dict(id=p['id'],sse=p['sse'],stream=known[sha(p['stream'])]) for p in cut['rows']]))
            expected=V1.distinct_whole(V1.whole_views(baseline,locals))
            if len(expected)!=len(original_parts):raise ValueError('The original five-recipe dedup changed')
            originals=[]
            for value,parts,stored,chain in zip(expected,original_parts,row['whole_rows'],row['whole_chains']):
                if value['blobs']!=parts or value['labels']!=stored['labels'] or value['id']!=stored['id']:
                    raise ValueError('The exact original recipe changed')
                ids=[]
                for blob,local in zip(parts,restricted):
                    candidates=[p['id'] for p in local['rows'] if old_stream(p['stream'])==blob]
                    if not candidates:raise ValueError('A protected recipe is outside the restricted pool')
                    ids.append(min(candidates))
                originals.append(dict(id=stored['id'],labels=list(stored['labels']),ids=ids,
                    segments=chain['segments'],old_value=stored))
            jobs.append(dict(id=row['id'],baseline_id=base['id'],arm=row['arm'],profile=row['profile'],
                source_ordinal=row['source_ordinal'],nonspeech=row['nonspeech'],mode=row['mode'],
                baseline_bytes=row['baseline_bytes'],caps=row['whole_caps'],baseline=base['segments'],
                base=base,pools=restricted,originals=originals,
                v1_raw_audit_cost=[local['independent_raw_pool_model_sse_audit_cost'] for local in row['locals']]))
    jobs.sort(key=lambda j:j['id']);validate_jobs(jobs)
    bridge=verify_v1_bridge(bindings,args.source_root,inventory,inputs)
    natives,native_bridge=SUPPORT.bridge_native(args.source_root,args.native_cases,inputs)
    for binding in bindings:
        if binding['native_bridge']['library_sha256']!=native_bridge['library_sha256']:
            raise ValueError('The unchanged native library closure differs from V1')
    inputs.verify()
    if recipe!=sources():raise ValueError('Preparation sources changed')
    manifest=dict(schema='lpx-chain-rate-fixed-pools-private-v1',status='prepared-no-dp',
        producer_commit=PRODUCER,producer_root=str(args.source_root),production_sources=inventory,
        study_sources=recipe,input_files_sha256=inputs.pins,native_cases=str(args.native_cases),
        native_bridge=native_bridge,model_bridge=bridge,jobs=jobs,runtime=runtime_identity(),
        preparation_cost=elapsed(began),scope=dict(contexts=12,arm_records=60,reset_pools=100,
            planned_dp_calls=60,planned_cap_views=180,new_helpers=0,new_fits=0,new_native_builds=0))
    save(args.output/'manifest-private.json',manifest)
    save(args.output/'complete-private.json',dict(status='complete',manifest_sha256=sha((args.output/'manifest-private.json').read_bytes())))
    return manifest['scope']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','v1-root','v1-export','native-cases','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    for name in ('source_root','v1_root','v1_export','native_cases','output'):setattr(args,name,getattr(args,name).resolve())
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[name]='1'
    args.output=fresh_output(args.output)
    try:
        result=prepare(args);print(json.dumps(dict(status='prepared-no-dp',**result)),flush=True);return 0
    except Exception as exc:
        save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
