"""Export only anonymous completed-audit values and public source provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def read_record(study, phase, ordinal, profile):
    folder=study/'records'/phase/('source-%03d'%ordinal)/('profile-%d'%profile)
    raw=(folder/'record-private.json').read_bytes()
    marker=load(folder/'complete-private.json')
    if digest(raw)!=marker['report_sha256']:
        raise ValueError('A previously audited record changed')
    for name,expected in marker['artifacts_sha256'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or digest(path.read_bytes())!=expected:
            raise ValueError('A previously audited stream/journal changed')
    record=json.loads(raw)
    attempts=[load(p) for p in sorted((folder/'attempts').glob('attempt-*-private.json'))]
    if not attempts or attempts[-1]['status']!='complete':
        raise ValueError('A complete final attempt is required')
    return record,attempts[-1]


def work(record,attempt):
    events=attempt['operator_events']
    if len(events)!=record['actual_refinement_calls'] or any(e['status']!='complete' for e in events):
        raise ValueError('Actual stage journal differs')
    operators={}
    for event in events:
        item=operators.setdefault(event['operator'],dict(calls=0,wall_seconds=0.,cpu_seconds=0.,reported_seconds=0.,counters={}))
        item['calls']+=1
        item['wall_seconds']+=event['wall_seconds']
        item['cpu_seconds']+=event['cpu_seconds']
    for search in record['segment_searches']:
        for stage in search['report']['stages']:
            item=operators[stage['operator']]
            for name,value in stage['work'].items():
                if name=='seconds':
                    item['reported_seconds']+=value
                else:
                    item['counters'][name]=item['counters'].get(name,0)+int(value)
    wall=sum(e['wall_seconds'] for e in events)
    cpu=sum(e['cpu_seconds'] for e in events)
    return dict(actual_refinement_calls=len(events),operators=operators,
        stage_helper_wall_seconds=wall,stage_helper_cpu_seconds=cpu,
        record_workflow_wall_seconds=record['wall_seconds'],record_workflow_cpu_seconds=record['cpu_seconds'],
        nonhelper_workflow_wall_seconds=max(0.,record['wall_seconds']-wall),
        nonhelper_workflow_cpu_seconds=max(0.,record['cpu_seconds']-cpu))


def paired_comparison(rows,study):
    by_key={(row['phase'],row['source_ordinal'],row['profile']):row for row in rows}
    pairs=[]
    for deeper in (row for row in rows if row['phase']=='speech-default'):
        ordinal,profile=deeper['source_ordinal'],deeper['profile']
        shallow=by_key[('speech-screen',ordinal,profile)]
        for name in ('samples','mode','gain','original_complete_bytes','rollback_bytes'):
            if shallow[name]!=deeper[name]:
                raise ValueError('Paired target/control geometry differs')
        one,attempt_one=read_record(study,'speech-screen',ordinal,profile)
        four,attempt_four=read_record(study,'speech-default',ordinal,profile)
        if (one['target_reference_pcm16_sha256']!=four['target_reference_pcm16_sha256']
                or one['original_reference_pcm16_sha256']!=four['original_reference_pcm16_sha256']
                or one['chains'][0]['pcm16_sha256']!=four['chains'][0]['pcm16_sha256']):
            raise ValueError('Paired full source target/rollback differs')
        item=dict(source_ordinal=ordinal,profile=profile,samples=deeper['samples'],mode=deeper['mode'],gain=deeper['gain'],
            original_split=deeper['original_split'],
            targeted_not_independent_heldout=deeper['targeted_not_independent_heldout'],
            same_declared_target_and_rollback_verified=True,reset_segments=deeper['reset_segments'],
            search_work=dict(screen_1=work(one,attempt_one),default_4=work(four,attempt_four)),budgets=[])
        for old,new in zip(shallow['decisions'],deeper['decisions']):
            if old['percent']!=new['percent'] or old['cap']!=new['cap']:
                raise ValueError('Paired whole budget differs')
            both=old['role'] is not None and new['role'] is not None
            item['budgets'].append(dict(percent=old['percent'],cap=old['cap'],screen_1=old,default_4=new,
                default_rolls_back_where_screen_changes=old['changed_vs_rollback'] is True and new['role']=='control',
                joint_score_delta_4_minus_1=None if not both else new['score']-old['score'],
                serialized_byte_delta_4_minus_1=None if not both else new['bytes']-old['bytes'],
                pcm_sse_delta_4_minus_1=None if not both else new['pcm_sse']-old['pcm_sse'],
                pwm_sse_delta_4_minus_1=None if not both else new['pwm_sse']-old['pwm_sse']))
        pairs.append(item)
    if len(pairs)!=14:
        raise ValueError('The paired default subset must contain14 groups')
    budgets={}
    for index,percent in enumerate((100,95,90)):
        views=[row['budgets'][index] for row in pairs]
        both=[row for row in views if row['joint_score_delta_4_minus_1'] is not None]
        budgets[str(percent)]=dict(groups=14,screen_admissions=sum(v['screen_1']['role'] is not None for v in views),
            default_admissions=sum(v['default_4']['role'] is not None for v in views),
            only_screen_admitted=sum(v['screen_1']['role'] is not None and v['default_4']['role'] is None for v in views),
            only_default_admitted=sum(v['screen_1']['role'] is None and v['default_4']['role'] is not None for v in views),
            both_admitted=len(both),default_lower_joint_score=sum(v['joint_score_delta_4_minus_1'] < -1e-12 for v in both),
            default_equal_joint_score=sum(abs(v['joint_score_delta_4_minus_1']) <= 1e-12 for v in both),
            default_higher_joint_score=sum(v['joint_score_delta_4_minus_1'] > 1e-12 for v in both),
            default_rollback_where_screen_changed=[dict(source_ordinal=row['source_ordinal'],profile=row['profile'])
                for row in pairs if row['budgets'][index]['default_rolls_back_where_screen_changes']])
    timings={}
    for key in ('screen_1','default_4'):
        fields=('actual_refinement_calls','stage_helper_wall_seconds','stage_helper_cpu_seconds',
            'record_workflow_wall_seconds','record_workflow_cpu_seconds','nonhelper_workflow_wall_seconds','nonhelper_workflow_cpu_seconds')
        timings[key]={field:sum(row['search_work'][key][field] for row in pairs) for field in fields}
    return dict(schema='lpx-adaptive-paired-default-versus-screen-v1',groups=14,sources=7,
        targeted_groups=sum(row['targeted_not_independent_heldout'] for row in pairs),budgets=budgets,
        summed_paired_group_timing=timings,pairs=pairs,
        timing_scope='Actual helper intervals are journaled separately. Nonhelper workflow includes controller scoring, V1/seed rechecks, independent pool audit, native/whole metric validation and I/O; its audit-only portion was not separately instrumented. Summed per-record wall intervals are not campaign elapsed time.',
        quality_scope='Each delta compares the same source/profile/declared target/whole rollback and cap. No cross-level SSE aggregate or perceptual-quality claim.')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def write(path, value):
    if path.exists():
        raise ValueError('Public receipt output must be fresh')
    path.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf-8'))


def anonymous(value):
    if isinstance(value,dict):
        for name,entry in value.items():
            if any(term in name.casefold() for term in ('sha256','fingerprint','private_case','path')):
                raise ValueError('Private category in public numerical receipt')
            anonymous(entry)
    elif isinstance(value,list):
        for entry in value:
            anonymous(entry)
    elif isinstance(value,str):
        if re.fullmatch('[a-fA-F0-9]{64}',value) or re.search(r'[A-Za-z]:[/\\]|/Users/|/home/',value):
            raise ValueError('Private path or fingerprint in public numerical receipt')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',required=True,type=Path)
    parser.add_argument('--study',required=True,type=Path)
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    target=here.parent
    audit=load(args.audit/'audit.json')
    private=load(args.audit/'audit-private.json')
    rows=load(args.audit/'groups.json')
    binding_bytes=(args.study/'binding-private.json').read_bytes()
    binding=json.loads(binding_bytes)
    if (audit['status']!='passed' or private['status']!='passed'
            or audit['completed_records']!=118 or audit['expected_records']!=118
            or audit['missing_records']!=0 or not audit['all_final_worker_receipts_verified']
            or len(rows)!=118):
        raise ValueError('Full completed independent audit required')
    if private['binding_sha256']!=digest(binding_bytes) or private['auditor_sha256']!=digest((here/'audit_saved.py').read_bytes()):
        raise ValueError('Exact audit source/binding differs')
    for name,value in private.items():
        if name not in ('binding_sha256','auditor_sha256') and audit[name]!=value:
            raise ValueError('Public/private audit receipt values differ')
    for phase,count in (('speech-screen',98),('speech-default',14),('nonspeech-default',6)):
        if sum(row['phase']==phase for row in rows)!=count or audit['phases'][phase]['groups']!=count:
            raise ValueError('Predeclared phase counts differ')
    for row in rows:
        record,_=read_record(args.study,row['phase'],row['source_ordinal'],row['profile'])
        if row['phase']=='nonspeech-default':
            row['original_split']='nonspeech_control'
        elif record['split'] in ('tuning','evaluation','additional'):
            row['original_split']=record['split']
        else:
            raise ValueError('Unrecognized private source split must not be published')
    anonymous(audit)
    anonymous(rows)
    root=here.parents[4]
    sources={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in
             (here/'audit_saved.py',here/'test_audit_saved.py',Path(__file__))}
    runtime=binding['environment']
    source=dict(schema='lpx-adaptive-independent-audit-source-runtime-v1',
        core_commit=binding['core_commit'],
        auditor_revision=subprocess.check_output(['git','-C',str(root),'log','-1','--format=%H','--',
            (here/'audit_saved.py').relative_to(root).as_posix()],text=True).strip(),
        reproduction_sources_sha256=sources,validated_core_sources_sha256=binding['source']['core'],
        runtime=dict(python=runtime['python'].split()[0],packages=runtime['packages'],
            platform=runtime['platform'],compiler_version=runtime['compiler_version'],threads=runtime['threads']),
        omitted_private_categories=['input/media/PCM/stream/native-image fingerprints','input/output paths','original identifiers'],
        audit_wall_scope='includes read-only verification, cache reuse and bounded waits overlapping corpus generation')
    write(target/'audit.json',audit)
    write(target/'groups.json',rows)
    write(target/'source-runtime.json',source)
    paired=paired_comparison(rows,args.study)
    anonymous(paired)
    write(target/'paired-default-vs-screen.json',paired)
    splits={}
    for phase in ('speech-screen','speech-default','nonspeech-default'):
        splits[phase]={}
        for label in sorted({row['original_split'] for row in rows if row['phase']==phase}):
            subset=[row for row in rows if row['phase']==phase and row['original_split']==label]
            splits[phase][label]=dict(groups=len(subset),sources=len({row['source_ordinal'] for row in subset}),
                targeted_not_independent_heldout=sum(row['targeted_not_independent_heldout'] for row in subset),
                budgets={str(percent):dict(admissions=sum(row['decisions'][i]['role'] is not None for row in subset),
                    changed_vs_rollback=sum(row['decisions'][i]['changed_vs_rollback'] is True for row in subset))
                    for i,percent in enumerate((100,95,90))})
    write(target/'split-summary.json',dict(schema='lpx-adaptive-original-split-summary-v1',phases=splits,
        scope='Original split names are historical dataset labels, not proof of untouched or speaker-independent holdout. Targeted flags and paired-subset overlap remain explicit. Nonspeech control label is a public scope tag; original private metadata is retained in source records.'))
    print(json.dumps(dict(status='exported',records=len(rows),files=5)))


if __name__=='__main__':
    main()
