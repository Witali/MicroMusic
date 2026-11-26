"""Immutable, phased audiobook study orchestration. No automatic retries."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import study as s


def now():return datetime.now(timezone.utc).isoformat()


def code_files():
    return sorted(set([HERE/n for n in ('runner.py','study.py','validate.py','build.py','benchmark.cpp',
        'PROTOCOL.md','PHASES.md','prepare_sources.py')]+list((HERE/'tests').glob('*.py'))+list((HERE/'tests').glob('*.cpp'))))


def gate(path,schema):
    value=s.read(path)
    if value.get('schema')!=schema or not (value.get('passed') is True or value.get('status')=='PASS'):
        raise ValueError('Required independent gate has not passed')
    return value


def prepare(args):
    output=s.private(args.output);output.mkdir(parents=True,exist_ok=True)
    if (output/'freeze-private.json').exists():raise ValueError('Study already prepared; do not replace its freeze')
    manifest_path=Path(args.manifest).resolve();manifest=s.read(manifest_path)
    audit=gate(args.source_audit,'lpx-audiobook-independent-source-audit-v1')
    long=gate(args.long_gate,'lpx-audiobook-long-independent-v1')
    smoke=gate(args.smoke,'lpx-audiobook-adapter-synthetic-smoke-v1')
    build=s.read(args.build_receipt);s.builder.verify(build)
    if s.sha(HERE/'build.py')!=build['builder_source_sha256']:raise ValueError('Build recipe changed after compilation')
    if smoke['binary_sha256']!=build['binary_sha256'] or smoke['benchmark_sha256']!=s.sha(HERE/'benchmark.cpp'):
        raise ValueError('Synthetic smoke used a different executable/source')
    for name,expected in long['sources'].items():
        if s.sha(s.ROOT/name)!=expected:raise ValueError('Independent Long gate source changed')
    for name,key in (('LpxAccuracy.cpp','current_cpp'),('LpxAccuracy.h','current_h')):
        if s.sha(s.builder.ACTIVE/'host'/name)!=long['expected'][key]:raise ValueError('Long scope changed')
    if len(long['results'])!=6 or not all(v['passed'] for v in long['results'].values()):raise ValueError('Incomplete Long gate')
    if (manifest['schema']!='lpx-audiobook-twenty-second-sources-private-v1' or not manifest['prepared_before_encoding']
            or len(manifest['sources'])!=20 or manifest['preparer_sha256']!=s.sha(HERE/'prepare_sources.py')):
        raise ValueError('Unbound source preparation')
    if (audit['selected_sources']!=20 or audit['samples_each']!=s.SAMPLES or audit['rate']!=s.RATE
            or audit['source_manifest_sha256']!=s.sha(manifest_path)):
        raise ValueError('Source audit cohort differs')
    cases=[]
    for source in manifest['sources']:
        ordinal=source['ordinal']
        if (type(ordinal) is not int or not re.fullmatch(r'group-[0-9]+',source['source_group'])
                or source['split'] not in ('development','heldout') or source['samples']!=s.SAMPLES
                or source['rate']!=s.RATE or source['seconds']!=20 or source['start_seconds']!=120):
            raise ValueError('Unexpected frozen source geometry/membership')
        target=s.checked(manifest_path.parent,source['target_file'],source['target_sha256'])
        if target.stat().st_size!=s.SAMPLES*2:raise ValueError('Incomplete prepared target')
        cases.append(dict(ordinal=ordinal,split=source['split'],source_group=source['source_group'],
            target=str(target),target_sha256=source['target_sha256'],samples=s.SAMPLES,rate=s.RATE))
    cases.sort(key=lambda x:x['ordinal'])
    if ([x['ordinal'] for x in cases]!=list(range(20)) or Counter(x['split'] for x in cases)!=dict(development=12,heldout=8)
            or len({x['target_sha256'] for x in cases})!=20):raise ValueError('Cohort or split changed')
    groups={}
    for case in cases:
        if case['source_group'] in groups and groups[case['source_group']]!=case['split']:raise ValueError('Group crosses phase boundary')
        groups[case['source_group']]=case['split']
    # Prove that the prospective documents are the registered committed bytes.
    for name in ('PROTOCOL.md','PHASES.md','prepare_sources.py'):
        relative=(HERE/name).relative_to(s.ROOT).as_posix()
        registered=subprocess.check_output(['git','show',args.registration+':'+relative],cwd=s.ROOT)
        if registered!=(HERE/name).read_bytes():raise ValueError('Registered protocol/preparer changed')
    software={p.relative_to(s.ROOT).as_posix():s.sha(p) for p in code_files()}
    tests=subprocess.run([sys.executable,str(HERE/'tests/test_runner.py')],capture_output=True)
    (output/'runner-tests-private.log').write_bytes(tests.stdout+tests.stderr)
    if tests.returncode or software!={p.relative_to(s.ROOT).as_posix():s.sha(p) for p in code_files()}:
        raise ValueError('Runner tests failed or software changed during preparation')
    bindings={str(Path(p).resolve()):s.sha(p) for p in (args.manifest,args.source_audit,args.long_gate,args.smoke,args.build_receipt)}
    freeze=dict(schema='lpx-audiobook-study-freeze-private-v1',created_utc=now(),registration=args.registration,
        quality_target='pwm',samples=s.SAMPLES,rate=s.RATE,calls=4,max_workers=2,
        first_development_ordinal=min(x['ordinal'] for x in cases if x['split']=='development'),
        build_receipt=str(Path(args.build_receipt).resolve()),bindings=bindings,cases=cases,
        software=software,runner_tests=dict(passed=True,tests=4,log_sha256=s.sha(output/'runner-tests-private.log')),
        heldout_requires_explicit_final_policy_freeze=True,no_automatic_retries=True)
    s.write(output/'freeze-private.json',freeze,immutable=True)
    print(json.dumps(dict(status='FROZEN',cases=20,development=12,heldout_locked=8,
        pilot_ordinal=freeze['first_development_ordinal'],software_files=len(freeze['software']))))


def load(output):
    output=s.private(output);freeze_path=output/'freeze-private.json';freeze=s.read(freeze_path)
    if freeze['schema']!='lpx-audiobook-study-freeze-private-v1':raise ValueError('Unknown study freeze')
    for path,expected in freeze['bindings'].items():
        if s.sha(path)!=expected:raise ValueError('Frozen input/gate/build binding changed')
    for name,expected in freeze['software'].items():
        if s.sha(s.ROOT/name)!=expected:raise ValueError('Frozen study implementation changed')
    build=s.read(freeze['build_receipt']);s.builder.verify(build)
    for case in freeze['cases']:
        if s.sha(case['target'])!=case['target_sha256']:raise ValueError('Prepared target changed')
    return output,freeze,build


def case_folder(output,ordinal):return output/('case-%03d'%ordinal)


def command(build,source,prefix,verify=False):
    return s.builder.launch(build['distro'])+[s.builder.linux(build['binary'])]+(['--verify'] if verify else [])+[
        s.builder.linux(source),s.builder.linux(prefix)]


def run_case(output,freeze,build,case):
    folder=case_folder(output,case['ordinal']);folder.mkdir(parents=True,exist_ok=True)
    started=folder/'attempt-private.json';complete=folder/'complete-private.json'
    if started.exists() or complete.exists():raise ValueError('Case already attempted; automatic retry prohibited')
    s.write(started,dict(schema='lpx-audiobook-attempt-private-v1',ordinal=case['ordinal'],started_utc=now(),
        freeze_sha256=s.sha(output/'freeze-private.json'),target_sha256=case['target_sha256'],
        binary_sha256=build['binary_sha256']),immutable=True)
    prefix=folder/'run';t=time.perf_counter()
    try:
        child=subprocess.run(command(build,case['target'],prefix),capture_output=True)
        seconds=time.perf_counter()-t
        (folder/'encode-private.stdout').write_bytes(child.stdout);(folder/'encode-private.stderr').write_bytes(child.stderr)
        if child.returncode:raise ValueError('Native encode process failed')
        report=json.loads(child.stdout.decode('utf-8'));s.write(folder/'encode-private.json',report,immutable=True)
        artifacts,waveform=s.check_artifacts(report,case['target'],prefix)
        eligible=[s.finite(x) for x in report['baseline']['quality']['stoi']]
        v=time.perf_counter();replay=subprocess.run(command(build,case['target'],prefix,True),capture_output=True)
        verification_seconds=time.perf_counter()-v
        (folder/'verify-private.stdout').write_bytes(replay.stdout);(folder/'verify-private.stderr').write_bytes(replay.stderr)
        if replay.returncode:raise ValueError('Read-only native verification failed')
        verification=json.loads(replay.stdout.decode('utf-8'));s.check_verification(verification,report)
        s.write(folder/'verify-private.json',verification,immutable=True)
        if any(s.sha(folder/name)!=expected for name,expected in artifacts.items()):raise ValueError('Verification changed artifacts')
        load(output)  # Prove the inputs/executable/software stayed frozen across this case.
        value=dict(schema='lpx-audiobook-case-private-v1',status='PASS',ordinal=case['ordinal'],
            freeze_sha256=s.sha(output/'freeze-private.json'),completed_utc=now(),
            artifacts=artifacts,waveform=waveform,stoi_eligible=eligible,
            subprocess_wall_seconds=seconds,verification_wall_seconds=verification_seconds,
            report_sha256=s.sha(folder/'encode-private.json'),verify_sha256=s.sha(folder/'verify-private.json'))
        s.write(complete,value,immutable=True)
    except Exception:
        (folder/'failure-private.log').write_text(traceback.format_exc(),encoding='utf-8')
        s.write(folder/'failure-private.json',dict(schema='lpx-audiobook-failure-private-v1',status='FAIL',
            ordinal=case['ordinal'],failure_category='execution_or_validation',elapsed_wall_seconds=time.perf_counter()-t),immutable=True)
        return dict(ordinal=case['ordinal'],status='FAIL')
    return dict(ordinal=case['ordinal'],status='PASS',selected_changed=report['selected_changed'],
        baseline_seconds=report['baseline_component_seconds'],optional_seconds=report['optional_component_seconds'])


def completed(output,freeze,case):
    folder=case_folder(output,case['ordinal']);path=folder/'complete-private.json'
    if not path.exists():return None
    value=s.read(path)
    if value['freeze_sha256']!=s.sha(output/'freeze-private.json') or value['ordinal']!=case['ordinal']:
        raise ValueError('Case completion binding differs')
    if (s.sha(folder/'encode-private.json')!=value['report_sha256'] or s.sha(folder/'verify-private.json')!=value['verify_sha256']
            or any(s.sha(folder/name)!=expected for name,expected in value['artifacts'].items())):
        raise ValueError('Completed case artifacts changed')
    return value


def public_case(output,freeze,case):
    value=completed(output,freeze,case);result={k:case[k] for k in ('ordinal','split','source_group')}
    if value:
        report=s.read(case_folder(output,case['ordinal'])/'encode-private.json')
        result.update(status='PASS',report=s.public_report(report),waveform=value['waveform'],
            stoi_eligible=value['stoi_eligible'],subprocess_wall_seconds=value['subprocess_wall_seconds'],
            verification_wall_seconds=value['verification_wall_seconds'])
    elif (case_folder(output,case['ordinal'])/'attempt-private.json').exists():
        result.update(status='FAIL',failure_category='execution_or_validation')
    else:result.update(status='NOT_RUN')
    return result


def export(output,freeze,build,phase,destination):
    cases=[x for x in freeze['cases'] if (x['ordinal']==freeze['first_development_ordinal'] if phase=='pilot' else x['split']==phase)]
    rows=[public_case(output,freeze,case) for case in cases]
    valid_or_failed=[row for row in rows if row['status']!='NOT_RUN']
    result=dict(schema='lpx-audiobook-study-anonymous-v1',phase=phase,quality_target='pwm',active_paths=['pcm','pwm'],
        samples_each=s.SAMPLES,rate=s.RATE,expected_cases=len(cases),cases=rows,
        aggregate=s.aggregate(valid_or_failed,len(cases)),
        software=dict(sources=build['sources'],study_sources=freeze['software'],compiler=build['compiler'],
            options=build['options'],binary_sha256=build['binary_sha256'],environment=build['environment']),
        timing_scope=dict(component_cpu='native worker process CPU; independent codec process per case',
            component_wall='measured baseline and helper components; not automatic full API runtime',
            subprocess_wall='whole encoder worker including diagnostics and artifact output',
            verification_wall='separate read-only native/model/metric/selector replay',automatic_api_seconds=None),
        selection='unchanged production selector; research retention guards are posthoc diagnostics',
        source_privacy='anonymous source-group ordinals; source/media/target/artifact bindings remain private')
    s.write(destination,result)
    return result


def phase_run(args):
    output,freeze,build=load(args.output)
    if not 1<=args.workers<=freeze['max_workers']:raise ValueError('At most two independent codec processes')
    if args.phase=='pilot':
        cases=[c for c in freeze['cases'] if c['ordinal']==freeze['first_development_ordinal']]
        if args.workers!=1:raise ValueError('Pilot is one process')
    elif args.phase=='development':
        if not args.pilot_audit:raise ValueError('Independent immutable pilot audit is required')
        pilot=case_folder(output,freeze['first_development_ordinal'])/'complete-private.json'
        audit=gate(args.pilot_audit,'lpx-audiobook-pilot-independent-v1')
        if audit['freeze_sha256']!=s.sha(output/'freeze-private.json') or audit['pilot_completion_sha256']!=s.sha(pilot):
            raise ValueError('Pilot audit is not bound to this immutable pilot')
        cases=[c for c in freeze['cases'] if c['split']=='development' and c['ordinal']!=freeze['first_development_ordinal']]
    else:
        if not args.policy_freeze:raise ValueError('Heldout is locked until explicit root final-policy freeze')
        declaration=gate(args.policy_freeze,'lpx-audiobook-final-policy-freeze-v1')
        if (declaration.get('root_explicit_final_policy_frozen') is not True
                or declaration['freeze_sha256']!=s.sha(output/'freeze-private.json')
                or declaration['binary_sha256']!=build['binary_sha256']):raise ValueError('Heldout policy declaration differs')
        dev=[public_case(output,freeze,c) for c in freeze['cases'] if c['split']=='development']
        if any(x['status']!='PASS' for x in dev):raise ValueError('Development is incomplete')
        if declaration['development_completion_sha256']!=s.digest(s.encoded(dev)):
            raise ValueError('Policy declaration is not bound to all development outcomes')
        cases=[c for c in freeze['cases'] if c['split']=='heldout']
    # Refuse an ambiguous resumption/retry. Completed pilot is reused only in dev export.
    for case in cases:
        if (case_folder(output,case['ordinal'])/'attempt-private.json').exists():raise ValueError('Phase case already attempted')
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending=[executor.submit(run_case,output,freeze,build,case) for case in cases]
        for future in as_completed(pending):
            row=future.result();print(json.dumps(row),flush=True)
            export(output,freeze,build,args.phase,args.public)
    report=export(output,freeze,build,args.phase,args.public)
    if not report['aggregate']['complete']:raise ValueError('Phase retains a failure; no automatic retry')


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output',type=Path,required=True)
    for name in ('manifest','source-audit','long-gate','smoke','build-receipt'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--registration',default='fbc0c97d')
    p=sub.add_parser('run');p.add_argument('--output',type=Path,required=True);p.add_argument('--phase',choices=('pilot','development','heldout'),required=True)
    p.add_argument('--public',type=Path,required=True);p.add_argument('--workers',type=int,default=1)
    p.add_argument('--pilot-audit',type=Path);p.add_argument('--policy-freeze',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args)
    else:phase_run(args)


if __name__=='__main__':main()
