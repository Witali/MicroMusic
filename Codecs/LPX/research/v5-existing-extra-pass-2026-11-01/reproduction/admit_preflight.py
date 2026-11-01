"""Strict read-only admission before invoking the unchanged frozen producer.

This additional entry gate does not repeat the successful six-call v2 preflight.
Its own sources and receipts are separate from the producer's research snapshot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
TOP=HERE.parent
sys.path.insert(0,str(TOP))
import run_existing as producer
from extra_runtime import (Inputs,SOURCE_COMMIT,bind_production,bridge_native,load_manifest,
    production_snapshot,save,sha,source_snapshot)
from prepare_existing import current_runtime


def own_sources():
    names=('admit_preflight.py','test_preflight_admission.py','README.md')
    return {name:sha((HERE/name).read_bytes()) for name in names}


def clock():return time.perf_counter(),time.process_time()
def cost(start):return dict(wall_seconds=time.perf_counter()-start[0],cpu_seconds=time.process_time()-start[1])


def verify_preflight(path,manifest_path,inputs,expected):
    """Require closed same-context evidence and the identical prepared binding."""
    path=Path(path).resolve();manifest_path=Path(manifest_path).resolve()
    summary=inputs.json(path/'summary.json');proof=inputs.json(path/'binding-private.json')
    attempt=inputs.json(path/'attempt-private.json');synthetic=inputs.json(path/'synthetic-private.json')
    results=inputs.json(path/'results-private.json')
    if (summary['status']!='PASS' or summary['preflight_only'] is not True or summary['arm'] is not None or
            summary['arm_records']!=0 or summary['corpus_helper_calls']!=0 or summary['actual_cap_views']!=0 or
            summary['synthetic_helper_calls']!=6 or any(summary[name]!=0 for name in ('initial_fits','native_builds','target_jobs')) or
            attempt['status']!='complete' or attempt['helper_calls'] or attempt['records'] or
            attempt['forbidden_fit_or_build_attempts']!=0 or len(attempt['synthetic_calls'])!=6 or
            any(row['status']!='complete' for row in attempt['synthetic_calls']) or results!=[] or
            synthetic['status']!='PASS' or synthetic['helper_calls']!=6 or len(synthetic['calls'])!=6):
        raise ValueError('Required six-call synthetic-only preflight is not terminal complete')
    for name in ('source_commit','production_sources','research_sources','runtime','native_bridge','source_context'):
        if proof[name]!=expected[name]:raise ValueError('Preflight '+name+' differs from the current worker context')
    if (Path(proof['source_root']).resolve()!=Path(expected['source_root']).resolve() or
            proof['arm'] is not None or proof['assigned_jobs']!=[]):
        raise ValueError('Preflight source root or assigned numerical scope differs')
    if Path(proof['baselines_path']).resolve()!=manifest_path:
        raise ValueError('Preflight names a different prepared manifest path')
    digest=sha(inputs.read(manifest_path))
    if proof['input_files_sha256'].get(str(manifest_path))!=digest:
        raise ValueError('Preflight omitted or changed the pinned prepared manifest digest')
    return dict(status='PASS',preflight_path=str(path),prepared_manifest_path=str(manifest_path),
        prepared_manifest_sha256=digest,preflight_only=True,synthetic_helper_calls=6,corpus_helper_calls=0,
        exact_production_native_research_runtime=True,closed_summary_attempt_results=True,
        use='Strict admission of existing v2 proof; no repeated helper or relabelled old research source')


def prepare_admission(args,inputs):
    sources=source_snapshot();own=own_sources();manifest=load_manifest(args.baselines,inputs)
    inventory=bind_production(args.source_root,SOURCE_COMMIT)
    _,native=bridge_native(args.source_root,args.native_cases,inputs)
    runtime=current_runtime()
    if (manifest['source_commit']!=SOURCE_COMMIT or Path(manifest['source_root']).resolve()!=args.source_root or
            manifest['production_sources']!=inventory or manifest['native_bridge']!=native or manifest['runtime']!=runtime):
        raise ValueError('Prepared source/native/runtime context changed before strict admission')
    # No production imports are needed to compare the recorded runtime, byte
    # inventories or library closure. The producer loads its explicit root later.
    if Path(producer.__file__).resolve()!=TOP/'run_existing.py':
        raise ValueError('The frozen producer entry came from another package')
    context=sha(json.dumps(dict(source=inventory,native=native),sort_keys=True).encode())
    expected=dict(source_commit=SOURCE_COMMIT,source_root=str(args.source_root),production_sources=inventory,
        research_sources=sources,runtime=runtime,native_bridge=native,source_context=context)
    proof=verify_preflight(args.preflight,args.baselines,inputs,expected)
    if sources!=source_snapshot() or own!=own_sources() or inventory!=production_snapshot(args.source_root):
        raise ValueError('Admission or frozen producer source changed during checks')
    inputs.verify()
    return dict(schema='lpx-existing-extra-preflight-admission-private-v1',status='PASS',
        admission_commit=subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
        admission_sources=own,producer_source_commit=SOURCE_COMMIT,producer_research_sources=sources,
        production_sources=inventory,source_root=str(args.source_root),native_bridge=native,runtime=runtime,
        preflight_admission=proof,input_files_sha256=inputs.pins,
        historical_synthetic_calls=6,current_completed_preflight_calls=6,planned_worker_warm_calls=6,
        final_paid_synthetic_calls_planned=18,new_helper_calls=0,new_pcm_decodes=0,new_native_builds=0,
        worker_arm=args.arm,worker_output=None if args.output is None else str(args.output),
        admission_only=args.admission_only)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','baselines','native-cases','preflight','admission-output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--arm',choices=('legacy','causal'));parser.add_argument('--output',type=Path)
    parser.add_argument('--admission-only',action='store_true')
    args=parser.parse_args()
    for name in ('source_root','baselines','native_cases','preflight','admission_output','output'):
        value=getattr(args,name)
        if value is not None:setattr(args,name,value.resolve())
    if not args.admission_only and (args.arm is None or args.output is None):
        parser.error('A real worker requires its fixed arm and fresh output directory')
    private=(TOP.parents[3]/'build').resolve()
    if args.admission_output.exists() or not args.admission_output.is_relative_to(private):
        parser.error('Use a fresh private ignored admission directory')
    if args.output is not None and (args.output.exists() or not args.output.is_relative_to(private) or
            args.output==args.admission_output or args.output.is_relative_to(args.admission_output) or args.admission_output.is_relative_to(args.output)):
        parser.error('Use a separate fresh private ignored worker directory')
    args.admission_output.mkdir(parents=True);begin=clock();inputs=Inputs()
    save(args.admission_output/'attempt-private.json',dict(status='started',admission_only=args.admission_only,new_helper_calls=0))
    try:
        receipt=prepare_admission(args,inputs);receipt['admission_cost']=cost(begin)
        # This closed, source-bound proof is durable before producer.main runs.
        save(args.admission_output/'admission-private.json',receipt)
        save(args.admission_output/'complete-private.json',dict(status='complete',
            admission_sha256=sha((args.admission_output/'admission-private.json').read_bytes())))
        save(args.admission_output/'attempt-private.json',dict(status='complete',admission_only=args.admission_only,new_helper_calls=0))
        if args.admission_only:
            print(json.dumps(dict(status='PASS',admission_only=True,new_helper_calls=0,admission_cost=receipt['admission_cost'])),flush=True)
            return 0
        arguments=[str(TOP/'run_existing.py')]
        for name in ('source_root','baselines','native_cases','preflight','arm','output'):
            arguments.extend(('--'+name.replace('_','-'),str(getattr(args,name))))
        previous=sys.argv;started=clock()
        try:
            sys.argv=arguments
            result=producer.main()
            worker_cost=cost(started)
        finally:sys.argv=previous
        after=clock();inputs.verify()
        if (receipt['admission_sources']!=own_sources() or receipt['producer_research_sources']!=source_snapshot() or
                receipt['production_sources']!=production_snapshot(args.source_root)):
            raise ValueError('Source or admitted context changed during the real worker')
        save(args.admission_output/'worker-terminal-private.json',dict(status='complete' if result==0 else 'worker-failed',
            exit_code=result,worker_arm=args.arm,worker_output=str(args.output),worker_call_cost=worker_cost,
            post_admission_guard_cost=cost(after),entry_total_cost=cost(begin),admission_preparation_cost=receipt['admission_cost'],
            initial_admission_sha256=sha((args.admission_output/'admission-private.json').read_bytes())))
        save(args.admission_output/'attempt-private.json',dict(status='complete',admission_only=False,
            worker_status='complete' if result==0 else 'failed',worker_exit_code=result))
        return result
    except Exception as exc:
        save(args.admission_output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc(),total_cost=cost(begin)))
        save(args.admission_output/'attempt-private.json',dict(status='failed',exception_type=type(exc).__name__,admission_only=args.admission_only))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
