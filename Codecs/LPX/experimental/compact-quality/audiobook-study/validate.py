"""Read-only artifact/native replay and anonymous aggregate validation; no search."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import study as s
import runner as r


def one(output,freeze,build,case):
    value=r.completed(output,freeze,case)
    if value is None:raise ValueError('A required case has no successful immutable completion')
    folder=r.case_folder(output,case['ordinal']);report=s.read(folder/'encode-private.json')
    artifacts,waveform=s.check_artifacts(report,case['target'],folder/'run')
    if artifacts!=value['artifacts'] or waveform!=value['waveform']:raise ValueError('Artifact/waveform labels changed')
    before={name:s.sha(folder/name) for name in artifacts}
    started=time.perf_counter();child=subprocess.run(r.command(build,case['target'],folder/'run',True),capture_output=True)
    seconds=time.perf_counter()-started
    if child.returncode:raise ValueError('Read-only native replay failed')
    import json
    native=json.loads(child.stdout.decode('utf-8'));s.check_verification(native,report)
    if before!={name:s.sha(folder/name) for name in artifacts}:raise ValueError('Read-only replay modified artifacts')
    eligible=[s.finite(x) for x in report['baseline']['quality']['stoi']]
    if eligible!=value['stoi_eligible']:raise ValueError('STOI eligibility changed')
    return dict(ordinal=case['ordinal'],passed=True,artifact_checks=len(artifacts),native_outputs=3,
        full_native_pcm_pwm_eof_replays=3,read_only_verification_seconds=seconds)


def validate(args):
    output,freeze,build=r.load(args.output)
    if not 1<=args.workers<=2:raise ValueError('At most two independent native processes')
    report=s.read(args.public)
    if report['schema']!='lpx-audiobook-study-anonymous-v1' or report['phase'] not in ('pilot','development','heldout'):
        raise ValueError('Unknown phase report')
    phase=report['phase']
    cases=[c for c in freeze['cases'] if (c['ordinal']==freeze['first_development_ordinal'] if phase=='pilot' else c['split']==phase)]
    # Export to ignored scratch and compare the whole explicit whitelist, not only means.
    scratch=output/('regenerated-'+phase+'-private.json')
    regenerated=r.export(output,freeze,build,phase,scratch)
    if regenerated!=report:raise ValueError('Anonymous rows/aggregates/software do not reproduce')
    if not report['aggregate']['complete']:raise ValueError('Incomplete phase cannot pass validation')
    rows=[]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending=[executor.submit(one,output,freeze,build,c) for c in cases]
        for future in as_completed(pending):rows.append(future.result())
    r.load(output)
    result=dict(schema='lpx-audiobook-study-validation-anonymous-v1',passed=True,phase=phase,cases=len(cases),
        rows=sorted(rows,key=lambda x:x['ordinal']),
        aggregate_reproduction=True,anonymous_whitelist_reproduction=True,
        immutable_bindings=True,source_targets_rehashed=True,full_160000_sample_continuity=True,
        native_pcm_and_actual_pwm=True,native_eof=True,model_repack_exact=True,actual_B0=True,
        baseline_protected_optional_failures=True,production_selector_replayed=True,
        independent_python_long_bits_and_sse=True,no_encoding_or_search=True,
        artifacts_checked=sum(x['artifact_checks'] for x in rows),
        metric_scope='native study adapter remeasures complete diagnostics; Python independently recounts bits and PCM/PWM SSE')
    s.write(args.validation,result)
    # Private receipt binds public evidence without exposing media/artifact fingerprints.
    s.write(output/('validation-'+phase+'-private.json'),dict(schema='lpx-audiobook-validation-binding-private-v1',
        passed=True,freeze_sha256=s.sha(output/'freeze-private.json'),public_sha256=s.sha(args.public),
        validation_sha256=s.sha(args.validation),completion_sha256={str(c['ordinal']):s.sha(r.case_folder(output,c['ordinal'])/'complete-private.json') for c in cases}))
    print('PASS: %d continuous native/model cases; %d artifacts; no encoding/search'%(len(cases),result['artifacts_checked']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--public',type=Path,required=True);p.add_argument('--validation',type=Path,required=True)
    p.add_argument('--workers',type=int,default=1);validate(p.parse_args())
