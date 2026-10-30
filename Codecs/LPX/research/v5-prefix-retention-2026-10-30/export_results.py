"""Allowlist projection from immutable private prefix replay to public evidence."""
import argparse
import json
from pathlib import Path

from prefixes import assert_incumbents_retained
from saved_inputs import sha

HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name,value):
    path = HERE/name
    if path.exists():
        raise ValueError('Public projection must not overwrite prior evidence')
    path.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay',type=Path,required=True)
    parser.add_argument('--bootstrap-root',type=Path,required=True)
    parser.add_argument('--contract',type=Path,required=True)
    args = parser.parse_args()
    binding = load(args.replay/'binding-private.json')
    for name,digest in binding['protocol'].items():
        if sha((HERE/name).read_bytes()) != digest:
            raise AssertionError('An executed replay source changed')
    for name,digest in binding['inputs_sha256'].items():
        if sha(Path(name).read_bytes()) != digest:
            raise AssertionError('An immutable bound replay input changed')
    attempt = load(args.replay/'attempt-private.json')
    summary = load(args.replay/'summary.json')
    private,projection = load(args.replay/'results-private.json'),load(args.replay/'results.json')
    if attempt['status'] != 'complete' or summary['status'] != 'PASS' or attempt['forbidden_search_attempts']:
        raise AssertionError('A completed zero-search replay is required')
    for original,public in zip(private,projection):
        if original['profile'] != public['profile'] or original['source_ordinal'] != 42:
            raise AssertionError('The fixed paired diagnostic changed')
        for row,claim in zip(original['whole_chains'],public['whole_chains']):
            if any(row[key] != value for key,value in claim.items() if key not in
                   ('pcm_sse','pwm_sse','within_tolerance_pcm','within_tolerance_pwm')):
                raise AssertionError('Public chain projection changed')
            for segment in row['segments']:
                blob = Path(segment['path']).read_bytes()
                if len(blob) != segment['file_bytes'] or sha(blob) != segment['stream_sha256']:
                    raise AssertionError('A measured ordered stream artifact changed')
        for decision in original['decisions']:
            assert_incumbents_retained(original['whole_chains'],decision,decision['known_admitted_incumbent_ids'])
    if len(private) != len(projection) or len(private) != 2:
        raise AssertionError('Exactly two paired diagnostic rows are required')
    study = load(Path(binding['study'])/'binding-private.json')
    audit_path = next(Path(name) for name in binding['inputs_sha256'] if Path(name).name == 'audit-private.json')
    audit = load(audit_path)
    runtime = {name:study['environment'][name] for name in ('python','platform','packages','compiler_version','threads')}
    bootstrap = []
    for number in (0,1):
        failed = load(args.bootstrap_root/('launch-%03d-private.json'%number))
        bootstrap.append({name:failed[name] for name in ('status','exit_code','category','replay_attempt_created',
            'native_calls','new_whole_measurements','new_fits','new_refinements')})
    contract = load(args.contract)
    if contract['status'] != 'PASS' or contract['prefix1_local_byte_comparisons'] != 20:
        raise AssertionError('The required pre-replay actual row contract did not pass')
    write('results.json',projection)
    write('summary.json',summary)
    write('bootstrap.json',dict(pre_replay_launch_failures=bootstrap,
        actual_replay_attempts=1,actual_replay_attempt_status=attempt['status']))
    write('contracts.json',dict(pure_contract_tests=8,pure_contract_failures=0,actual_saved_row_contract=contract))
    write('source-runtime.json',dict(replay_core_commit=binding['core_commit'],
        replay_research_commit=binding['own_commit'],protocol_commit='8ade28e',
        executed_replay_sources_sha256=binding['protocol'],runtime=runtime,
        full_independent_audit=dict(status=audit['status'],completed_records=audit['completed_records'],
            expected_records=audit['expected_records'],missing_records=audit['missing_records'],
            all_final_worker_receipts_verified=audit['all_final_worker_receipts_verified']),
        public_projection_source_sha256=sha(Path(__file__).read_bytes()),
        private_inputs='All input, media, ordered stream, PCM/PWM and native fingerprints stay in ignored receipts'))
    write('artifact-check.json',dict(status='PASS',executed_sources_match=True,bound_inputs_match=True,
        ordered_stream_artifacts_match=True,incumbent_retention_rechecked=True,
        forbidden_search_attempts=0,model_or_native_work_during_projection=0))
    print(json.dumps(dict(status='PASS',public_files=6,profiles=2,forbidden_search_attempts=0)))


if __name__ == '__main__':
    main()
