"""Private latest-B0 runner and strictly anonymous joint2 report exporter."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

# Set the same numerical runtime as the prior runner BEFORE joint imports NumPy.
for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[variable]='1'

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parents[1]/'sparse2'))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('command',choices=('prepare','pilot','all','export'))
parser.add_argument('--packages',type=Path);parser.add_argument('--previous',type=Path)
parser.add_argument('--output',type=Path,required=True);parser.add_argument('--public',type=Path)


def setup(packages):
    if packages:sys.path.insert(0,str(packages.resolve()))
    global j,prev,np,sparse,NativeReceiver,REPO,NATIVE_OUTPUT
    import joint as j
    import run_campaign as prev
    prev.initialize(packages)
    np,sparse,NativeReceiver,REPO,NATIVE_OUTPUT=prev.np,prev.sparse,prev.NativeReceiver,prev.REPO,prev.OUTPUT


def sources():
    result=prev.software()
    for name in ('joint.py','test_joint.py','run_study.py','PROTOCOL.md'):
        path=HERE/name;result[path.relative_to(REPO).as_posix()]=prev.digest(path.read_bytes())
    return result


def prepare(args):
    out=prev.private_output(args.output);previous=prev.private_output(args.previous)
    if out.exists():raise ValueError('Use a fresh ignored output')
    before=sources();wall=time.perf_counter();cpu=time.process_time()
    tests=prev.read(REPO/'build/compact-quality/sparse2-joint-tests/tests.json')
    if tests['status']!='PASS' or any(tests['source_hashes'][n]!=prev.digest((HERE/n).read_bytes())
                                    for n in ('joint.py','test_joint.py','PROTOCOL.md')):
        raise ValueError('Current source needs a passing complete synthetic gate')
    prior_freeze=prev.frozen(previous)
    # Read-only old exporter verifies ALL prior immutable artifacts and case
    # receipts, not merely a mutable convenience filename.
    prior_public=prev.export(previous,None)
    if prior_public['completed_cases']!=27:raise ValueError('Expected complete previous27')
    out.mkdir(parents=True)
    cases=[]
    for prior_case in prior_freeze['cases']:
        ordinal=prior_case['ordinal'];old=previous/('case-%03d'%ordinal)
        pointer=prev.read(old/'result-pointer-private.json')
        receipt_file=prev.checked(old,pointer['receipt_file'],pointer['receipt_sha256'])
        receipt=prev.read(receipt_file);selected=receipt['variants']['exhaustive']['final']
        if (pointer['selected_file']!='final-exhaustive.lpx' or pointer['selected_sha256']!=selected['sha256']
                or receipt['source_freeze_sha256']!=prev.digest(prev.encoded(prior_freeze))):
            raise ValueError('Latest exhaustive baseline pointer changed')
        blob=prev.checked(old,pointer['selected_file'],pointer['selected_sha256']).read_bytes()
        target=(old/'target.pcm16').read_bytes()
        if (prev.digest(target)!=prior_case['target']['target_sha256'] or len(blob)!=receipt['bytes']
                or len(target)!=64000 or len(blob)>1000):raise ValueError('Latest B0 or exact target changed')
        folder=out/('case-%03d'%ordinal);folder.mkdir()
        (folder/'baseline.lpx').write_bytes(blob);(folder/'target.pcm16').write_bytes(target)
        cases.append(dict(ordinal=ordinal,group=prior_case['group'],split=prior_case['split'],kind=prior_case['kind'],
            previous_pointer=str(old/'result-pointer-private.json'),previous_pointer_sha256=prev.digest((old/'result-pointer-private.json').read_bytes()),
            previous_receipt=str(receipt_file),previous_receipt_sha256=pointer['receipt_sha256'],
            baseline_sha256=pointer['selected_sha256'],target_sha256=prior_case['target']['target_sha256'],
            bytes=len(blob),samples=32000,saved_metrics=selected['metrics'],saved_bands=selected['bands'],
            declared_level=prior_case['target']['level']))
    binding=dict(cases=27,latest_admitted_exhaustive_baselines=sum(
        c['variants']['exhaustive']['final']['changed'] for c in prior_public['cases']),
        targets_unchanged=True,prior_complete_receipts_and_artifacts_verified=True,
        original_preprocessing_independently_rerun=False,original_declared_auto_quiet_retained=True)
    freeze=dict(schema='lpx-sparse2-joint-freeze-v1',sources=before,runtime=prev.runtime(),
        native_build=prev.read(NATIVE_OUTPUT/'build.json'),cases=cases,previous=str(previous),
        stoi_eligible=prior_freeze['stoi_eligible'],binding=binding,synthetic_tests=tests)
    prev.write(out/'freeze-private.json',freeze)
    warm=time.perf_counter()
    from test_joint import witness
    synthetic,_=witness();j.Context(synthetic)
    warm_seconds=time.perf_counter()-warm
    with NativeReceiver('common') as common,NativeReceiver('v5-only') as only:
        receiver=j.old.bridge_receiver(common,only)
        for case in cases:
            folder=out/('case-%03d'%case['ordinal'])
            blob=(folder/'baseline.lpx').read_bytes();reference=np.frombuffer((folder/'target.pcm16').read_bytes(),dtype='<i2').copy()
            context=j.Context(blob);pcm,duty=j.old._oracle(receiver,blob,context.base.pcm)
            measure,bands=prev.measure_context(reference);fresh=measure(pcm,case['ordinal']<20);frequency=bands(pcm)
            if fresh!=case['saved_metrics'] or frequency!=case['saved_bands']:
                raise ValueError('Fresh latest-B0 baseline metrics differ from prior admitted result')
            (folder/'baseline.pcm16').write_bytes(pcm.astype('<i2').tobytes());(folder/'baseline.pwm8').write_bytes(duty.tobytes())
            prev.write(folder/'baseline-private.json',dict(metrics=fresh,bands=frequency,binding=case,
                native_common_and_v5_only_pcm_pwm_exact=True))
            print(json.dumps(dict(stage='latest_baseline_verified',ordinal=case['ordinal'])),flush=True)
    if sources()!=before:raise ValueError('Source changed during preparation')
    prev.write(out/'prepared-private.json',dict(status='PASS',binding=binding,wall_seconds=time.perf_counter()-wall,
        python_process_cpu_seconds=time.process_time()-cpu,synthetic_context_warmup_seconds=warm_seconds,
        full_metric_evaluations=27,frequency_domain_evaluations=54,native_requests_each_receiver=54,
        cpu_scope='Python process only; excludes WSL native CPU'))
    print(json.dumps(dict(stage='prepared',cases=27)),flush=True)


def frozen(out):
    freeze=prev.read(out/'freeze-private.json')
    if freeze['sources']!=sources() or freeze['runtime']!=prev.runtime():raise ValueError('Frozen source/runtime changed')
    if prev.read(out/'prepared-private.json')['status']!='PASS':raise ValueError('Baseline preparation incomplete')
    if prev.read(NATIVE_OUTPUT/'build.json')!=freeze['native_build']:raise ValueError('Native build changed')
    for case in freeze['cases']:
        folder=out/('case-%03d'%case['ordinal'])
        if (prev.digest((folder/'baseline.lpx').read_bytes())!=case['baseline_sha256']
                or prev.digest((folder/'target.pcm16').read_bytes())!=case['target_sha256']):
            raise ValueError('Latest protected baseline or exact target changed')
    return freeze


def run_case(out,case,receiver,freeze):
    wall,cpu=time.perf_counter(),time.process_time();ordinal=case['ordinal'];folder=out/('case-%03d'%ordinal)
    if (folder/'complete-private.json').exists():raise ValueError('A case may be searched only once')
    blob=(folder/'baseline.lpx').read_bytes();target=np.frombuffer((folder/'target.pcm16').read_bytes(),dtype='<i2').copy()
    baseline=prev.read(folder/'baseline-private.json')
    start=time.perf_counter();result=j.search(target,blob,receiver);search_seconds=time.perf_counter()-start
    start=time.perf_counter();selected,journal=j.admit(target,result,speech=ordinal<20);admission_seconds=time.perf_counter()-start
    if journal['baseline']!=baseline['metrics']:raise ValueError('Admission changed the protected baseline')
    _,bands=prev.measure_context(target);artifacts={};regions=[];leaves=[]
    for region in result.regions:
        regions.append(dict(frame=region.frame,metadata=region.metadata,metadata_screen=region.metadata_screen,
            pools=[dict(packet=p.packet,symbols=p.symbols,winners=p.winners,losses=p.losses) for p in region.pools],
            queried={arm:[p.ordinal for p in points] for arm,points in region.queried.items()},
            endpoints={arm:p.ordinal for arm,p in region.endpoints.items()},query_attempts=region.query_attempts))
        for point in region.points:
            name='frame-%03d-point-%03d.lpx'%(point.frame,point.ordinal);(folder/name).write_bytes(point.blob)
            artifacts[name]=prev.digest(point.blob)
            leaves.append(dict(file=name,sha256=artifacts[name],frame=point.frame,ordinal=point.ordinal,
                metadata_index=point.metadata_index,parameters=point.parameters,symbols=point.symbols,pcm_sse=point.pcm_sse,
                pcm_sha256=prev.digest(point.pcm.astype('<i2').tobytes()),pwm_sha256=prev.digest(point.pwm.tobytes())))
    variants={}
    for arm in j.ARMS:
        values={}
        for kind,point in (('raw',result.raw[arm]),('final',selected[arm])):
            artifacts.update(prev.save_candidate(folder,kind+'-'+arm,point))
            metrics=journal['baseline'] if point.blob==blob else next(r['metrics']
                for r in journal['candidates'][arm] if r['sha256']==prev.digest(point.blob))
            if ordinal in freeze['stoi_eligible'] and any(metrics['metrics'][d]['stoi'] is None for d in ('pcm16','pwm8')):
                raise ValueError('Original eligible STOI score became missing')
            values[kind]=dict(metrics=metrics,bands=bands(point.pcm),changed=point.blob!=blob,
                pcm_changed_samples=int(np.count_nonzero(point.pcm!=result.baseline.pcm)),
                pwm_changed_samples=int(np.count_nonzero(point.pwm!=result.baseline.pwm)),
                frame=point.frame,metadata_index=point.metadata_index,parameters=point.parameters,
                symbols=point.symbols,sha256=prev.digest(point.blob))
        variants[arm]=values
    counters=dict(result.counters)
    counters.update(baseline_snapshot_samples=len(target),independent_model_samples=len(target)*result.counters['model_checks'],
        native_requests_each_receiver=2*result.counters['native_oracle_calls'],
        native_output_samples_both_receivers_domains=4*len(target)*result.counters['native_oracle_calls'],
        metric_proposal_attempts=journal['metric_proposal_attempts'],unique_metric_evaluations=journal['unique_metric_evaluations'],
        frequency_domain_evaluations=journal['unique_metric_evaluations']+12,retained_artifacts=len(artifacts))
    receipt=dict(schema='lpx-sparse2-joint-complete-private-v1',status='PASS',ordinal=ordinal,group=case['group'],split=case['split'],
        bytes=len(blob),samples=len(target),source_freeze_sha256=prev.digest(prev.encoded(freeze)),binding=case,
        baseline=baseline,variants=variants,regions=regions,leaves=leaves,admission=journal,counters=counters,artifacts=artifacts,
        search_seconds=search_seconds,admission_seconds=admission_seconds,wall_seconds=time.perf_counter()-wall,
        python_process_cpu_seconds=time.process_time()-cpu,cpu_scope='Python process only; excludes WSL native CPU')
    if sources()!=freeze['sources']:raise ValueError('Source changed during search')
    prev.write(folder/'complete-private.json',receipt)
    prev.write(folder/'result-pointer-private.json',dict(receipt_file='complete-private.json',
        receipt_sha256=prev.digest((folder/'complete-private.json').read_bytes()),selected_file='final-joint.lpx',
        selected_sha256=variants['joint']['final']['sha256']))
    print(json.dumps(dict(stage='case_complete',ordinal=ordinal,changes={a:variants[a]['final']['changed'] for a in j.ARMS},
        wall_seconds=receipt['wall_seconds'])),flush=True)


def public_case(receipt):
    variants={arm:{kind:dict(changed=row['changed'],pcm_changed_samples=row['pcm_changed_samples'],
        pwm_changed_samples=row['pwm_changed_samples'],**prev.numeric_summary(row['metrics'],row['bands']))
        for kind,row in values.items()} for arm,values in receipt['variants'].items()}
    rejected={}
    for arm,rows in receipt['admission']['candidates'].items():
        count=Counter()
        for row in rows:
            for key,passed in row['floors'].items():
                if not passed:count[key]+=1
            if all(row['floors'].values()) and not row['selected_at_step']:count['joint_objectives_or_better_already']=count.get('joint_objectives_or_better_already',0)+1
        rejected[arm]=dict(count)
    return dict(ordinal=receipt['ordinal'],group=receipt['group'],split=receipt['split'],bytes=receipt['bytes'],samples=receipt['samples'],
        baseline=prev.numeric_summary(receipt['baseline']['metrics'],receipt['baseline']['bands']),variants=variants,
        rejection_counts=rejected,counters=receipt['counters'],search_seconds=receipt['search_seconds'],
        admission_seconds=receipt['admission_seconds'],wall_seconds=receipt['wall_seconds'],
        python_process_cpu_seconds=receipt['python_process_cpu_seconds'])


def export(out,destination):
    freeze=frozen(out);cases=[]
    for case in freeze['cases']:
        folder=out/('case-%03d'%case['ordinal']);pointer=folder/'result-pointer-private.json'
        if not pointer.exists():continue
        p=prev.read(pointer);receipt=prev.read(prev.checked(folder,p['receipt_file'],p['receipt_sha256']))
        if (receipt['source_freeze_sha256']!=prev.digest(prev.encoded(freeze)) or p['selected_file']!='final-joint.lpx'
                or p['selected_sha256']!=receipt['variants']['joint']['final']['sha256']):
            raise ValueError('Case pointer differs from frozen joint output')
        for relative,expected in receipt['artifacts'].items():prev.checked(folder,relative,expected)
        cases.append(public_case(receipt))
    subsets={'all':cases,'all_speech':[c for c in cases if c['ordinal']<20]}
    subsets.update({name:[c for c in cases if c['split']==name] for name in ('tuning_speech','heldout_speech','negative_controls')})
    subsets.update({name:[c for c in cases if c['group']==name] for name in set(prev.summary.EXPECTED_GROUPS)})
    groups={}
    for name,subset in sorted(subsets.items()):
        groups[name]=dict(baseline=prev.aggregate(subset,lambda c:c['baseline'],freeze['stoi_eligible']),
            variants={arm:{kind:prev.aggregate(subset,lambda c,a=arm,k=kind:c['variants'][a][k],freeze['stoi_eligible'])
                      for kind in ('raw','final')} for arm in j.ARMS},
            changed={arm:sum(c['variants'][arm]['final']['changed'] for c in subset) for arm in j.ARMS})
    report=dict(schema='lpx-sparse2-joint-anonymous-v1',completed_cases=len(cases),expected_cases=27,cases=cases,groups=groups,
        implementation_sources=freeze['sources'],runtime=freeze['runtime'],binding_validation=freeze['binding'],
        original_stoi_eligible_ordinals=freeze['stoi_eligible'],preparation=prev.read(out/'prepared-private.json'),
        cpu_scope='Python-process CPU only; total case wall time includes native IPC',
        scope='One fixed pass against latest admitted B0, exact target/bytes/old floors; no listening or AVR claim')
    if destination:
        destination=destination.resolve();destination.relative_to(HERE.resolve());prev.write(destination,report)
    return report


def main(args):
    setup(args.packages);out=prev.private_output(args.output)
    try:
        if args.command=='prepare':
            if not args.previous:raise ValueError('Previous completed study is required')
            prepare(args);return 0
        freeze=frozen(out)
        if args.command in ('pilot','all'):
            cases=freeze['cases'] if args.command=='all' else [next(c for c in freeze['cases'] if c['split']=='tuning_speech')]
            with NativeReceiver('common') as common,NativeReceiver('v5-only') as only:
                receiver=j.old.bridge_receiver(common,only)
                for case in cases:
                    if (out/('case-%03d'%case['ordinal'])/'result-pointer-private.json').exists():continue
                    run_case(out,case,receiver,freeze)
        report=export(out,args.public)
        if args.command=='all' and report['completed_cases']!=27:raise ValueError('All27 cases are required')
        print(json.dumps(dict(stage='exported',completed_cases=report['completed_cases'])),flush=True);return 0
    except BaseException as error:
        if out.exists():(out/'infrastructure-error-private.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(json.dumps(dict(status='INFRASTRUCTURE_STOP',exception=type(error).__name__)),flush=True);return 2


if __name__=='__main__':sys.exit(main(parser.parse_args()))
