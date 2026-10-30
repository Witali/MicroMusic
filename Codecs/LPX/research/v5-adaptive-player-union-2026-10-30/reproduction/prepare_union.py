"""Read-only finite estimate of changed automatic V2 whole selections.

This command cannot build or simulate an image. Its private estimate is not an
admission handoff; final preparation also requires the independent audit gate.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import traceback

THIS = Path(__file__).resolve()
HERE = THIS.parent
PROTOCOL = HERE.parent/'PROTOCOL.md'
HELPERS = HERE.parents[1]/'v5-adaptive-target-player-2026-10-30/reproduction'
sys.path.insert(0,str(HELPERS))
from admit import Epoch, canonical, sha

PHASES = ('speech-screen','speech-default','nonspeech-default')
FLASH_BYTES = 32768


class Union:
    def __init__(self, parse):
        self.parse = parse
        self.registry = {}
        self.inputs = {}
        self.comparisons = {}
        self.records = {}

    def read(self,path,expected=None):
        path=Path(path).resolve(); raw=path.read_bytes(); digest=sha(raw)
        if expected is not None and digest!=expected:
            raise ValueError('An immutable input changed')
        if str(path) in self.inputs and self.inputs[str(path)]!=digest:
            raise ValueError('A previously observed input changed')
        self.inputs[str(path)]=digest
        return raw

    def chain(self,entry,profile):
        streams=[]; position=0
        for index,part in enumerate(entry['segments']):
            blob=self.read(part['path'],part['stream_sha256'])
            if (part['index']!=index or part['start']!=position or part['profile']!=profile
                    or len(blob)!=part['file_bytes'] or self.parse(blob)[:2]!=(part['samples'],profile)):
                raise ValueError('Stored ordered-chain geometry changed')
            position+=part['samples']; streams.append(blob)
        if not streams or position!=entry['samples'] or sum(map(len,streams))!=entry['stream_bytes']:
            raise ValueError('Full chain length or byte total changed')
        return tuple(streams)

    def register(self,entry,profile,key,role):
        if key not in self.registry:
            normalized={name:entry[name] for name in ('samples','segments','pcm16_sha256','pwm_sha256')}
            normalized.update(profile=profile,file_bytes=entry['stream_bytes'])
            self.registry[key]=dict(id='chain-%03d'%(len(self.registry)+1),entry=normalized,roles=[])
        item=self.registry[key]
        for field in ('samples','pcm16_sha256','pwm_sha256'):
            if item['entry'][field]!=entry[field]:
                raise ValueError('Byte-identical chains have conflicting declared output')
        if role not in item['roles']:item['roles'].append(role)
        return item['id']

    def add_record(self,record):
        control=next(entry for entry in record['chains'] if entry and entry['role']=='control')
        original=self.chain(control,record['profile'])
        counts=dict(observed=0,changed=0,unchanged=0,no_automatic_selection=0)
        if [budget['percent'] for budget in record['budgets']] != [100,95,90]:
            raise ValueError('The three declared budgets changed')
        for budget in record['budgets']:
            if budget['percent'] not in (100,95,90):raise ValueError('Unexpected budget')
            counts['observed']+=1
            if budget['selected'] is None:
                counts['no_automatic_selection']+=1; continue
            chosen=next(entry for entry in record['chains'] if entry and entry['role']==budget['selected'])
            if not chosen['automatic_quality_eligible'] or chosen['stream_bytes']>budget['cap']:
                raise ValueError('An ineligible or oversized raw tradeoff was selected')
            candidate=self.chain(chosen,record['profile'])
            if candidate==original:
                counts['unchanged']+=1; continue
            counts['changed']+=1
            old=self.register(control,record['profile'],original,'declared-level-rollback')
            new=self.register(chosen,record['profile'],candidate,'changed-automatic-selection')
            context=(record['speech'],record['source_ordinal'],record['profile'],record['mode'],
                     record['level']['gain'],old,new)
            if context not in self.comparisons:
                self.comparisons[context]=dict(id='comparison-%03d'%(len(self.comparisons)+1),
                    rollback_chain=old,candidate_chain=new,profile=record['profile'],
                    cohort='speech' if record['speech'] else 'nonspeech',source_ordinal=record['source_ordinal'],
                    mode=record['mode'],input_gain=record['level']['gain'],
                    reference_domain='declared-auto-target' if record['mode']=='auto-quiet' else 'original-level',
                    targeted_not_independent_heldout=record['targeted_not_independent_heldout'],
                    perceptual_adoption=False,selections=[])
            self.comparisons[context]['selections'].append(dict(phase=record['phase'],
                percent=budget['percent'],cap=budget['cap'],role=budget['selected']))
        return counts


def same(actual,expected):
    if isinstance(expected,float):
        return isinstance(actual,(int,float)) and math.isfinite(actual) and abs(actual-expected)<=1e-12
    return actual==expected


def audit_gate(args,union,binding,workers,stats):
    if stats['missing_records'] or not stats['all_six_workers_complete']:
        raise ValueError('All records and six terminal worker receipts are required')
    private=json.loads(union.read(args.audit/'audit-private.json'))
    public=json.loads(union.read(args.audit/'audit.json'))
    groups=json.loads(union.read(args.audit/'groups.json'))
    assert private['schema']=='lpx-adaptive-independent-audit-v1' and private['status']=='passed'
    assert private['completed_records']==private['expected_records']==118 and private['missing_records']==0
    assert private['all_final_worker_receipts_verified'] and private['binding_sha256']==sha((args.study/'binding-private.json').read_bytes())
    assert private['source_core_commit']==binding['core_commit']=='5a6cd1ab9593cac6f7e81756a639fa11d6c21276'
    assert private['auditor_sha256']==sha(union.read(args.auditor_source))
    assert [private['phases'][p]['groups'] for p in PHASES]==[98,14,6]
    for name,value in private.items():
        if name not in ('binding_sha256','auditor_sha256'):assert public[name]==value
    assert len(groups)==118
    indexed={(g['phase'],g['source_ordinal'],g['profile']):g for g in groups}
    assert len(indexed)==118
    for key,record in union.records.items():
        group=indexed[key]
        for name,value in dict(samples=record['samples'],reset_segments=len(record['chains'][0]['segments']),
            mode=record['mode'],gain=record['level']['gain'],targeted_not_independent_heldout=record['targeted_not_independent_heldout']).items():
            assert group[name]==value
        control=next(c for c in record['chains'] if c and c['role']=='control')
        assert group['rollback_bytes']==control['stream_bytes']
        for budget,decision in zip(record['budgets'],group['decisions']):
            for name,value in dict(percent=budget['percent'],cap=budget['cap'],role=budget['selected'],raw_tradeoff=budget['raw_tradeoff'],no_fit=budget['no_fit']).items():assert decision[name]==value
            chosen=None if budget['selected'] is None else next(c for c in record['chains'] if c and c['role']==budget['selected'])
            assert decision['bytes']==(None if chosen is None else chosen['stream_bytes'])
            if chosen is not None:
                assert decision['changed_vs_rollback']==(union.chain(chosen,record['profile'])!=union.chain(control,record['profile']))
                for name,value in dict(score=chosen['score'],rollback_score=control['score'],
                    pcm_sse=chosen['metrics']['pcm16']['error_energy'],pwm_sse=chosen['metrics']['pwm8']['error_energy'],
                    pcm_stoi=chosen['metrics']['pcm16']['stoi'],pwm_stoi=chosen['metrics']['pwm8']['stoi'],
                    within_tolerance_pcm=chosen['voice']['within_tolerance_frames'],within_tolerance_pwm=chosen['pwm_voice']['within_tolerance_frames']).items():assert same(decision[name],value)
    for info in workers:
        worker=json.loads(union.read(args.study/'workers'/(info['phase']+'-shard-%d-private.json'%info['shard'])))
        expected=[j for j in binding['jobs'] if j['phase']==info['phase'] and j['source_ordinal']%2==info['shard']]
        assert worker['status']=='complete' and worker['new_seed_fit_attempts']==0
        assert worker['executed_records']+worker['reused_records']==len(expected)==len(worker['records'])
        for job,row in zip(expected,worker['records']):
            records=binding['speech_records'] if job['speech'] else binding['nonspeech_records']
            key=(job['phase'],job['source_ordinal'],records[job['record_index']]['profile'])
            assert row==union.records[key]
    prepared=json.loads(union.read(args.prepared))
    assert prepared['source_inventory']==stats.pop('_consumer_inventory')
    assert prepared['dispatcher_sha256']==sha(Path(sys.modules['admit'].__file__).read_bytes())
    for prior in args.prior:
        receipt=json.loads(union.read(prior/'results-private.json'))
        assert receipt['status']=='complete'
    accepted=json.loads(union.read(args.expect_scope))
    for key in ('observed_complete_records','missing_records','automatic_changed_selection_views',
        'unchanged_selection_views_skipped','no_automatic_selection_views','distinct_union_chains',
        'distinct_candidate_chains','distinct_rollback_chains','distinct_comparisons','logical_image_rows',
        'data_alone_no_fit_rows','maximum_new_build_attempts','potential_full_playback_samples','maximum_chain_segments'):
        assert accepted[key]==stats[key]
    return dict(private_audit_path=str((args.audit/'audit-private.json').resolve()),
        auditor_source=str(args.auditor_source),prepared_path=str(args.prepared),prior_paths=list(map(str,args.prior)))


def estimate(args):
    epoch=Epoch(args.source_root)
    union=Union(epoch.modules['speech_compact'].unpack)
    raw=union.read(args.study/'binding-private.json'); binding=json.loads(raw)
    assert binding['identity']==sha(canonical({k:v for k,v in binding.items() if k!='identity'}))
    assert len(binding['jobs'])==118 and set(binding['expected'])==set(PHASES)
    consumer={name:digest for name,digest in epoch.snapshot().items() if name.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
    producer={name:digest for name,digest in binding['source']['core'].items() if name.startswith('Codecs/LPX/01_ACTIVE_Q0_CODEC/src/')}
    assert consumer==producer
    observed={phase:dict(records=0,observed=0,changed=0,unchanged=0,no_automatic_selection=0) for phase in PHASES}
    workers=[]
    for phase in PHASES:
        for shard in (0,1):
            path=args.study/'workers'/(phase+'-shard-%d-private.json'%shard)
            worker=json.loads(path.read_bytes()) if path.exists() else None
            if worker is not None:assert worker['identity']==binding['identity'] and worker['binding_sha256']==sha(raw)
            workers.append(dict(phase=phase,shard=shard,status='missing' if worker is None else worker['status'],
                records=0 if worker is None else len(worker['records'])))
    missing=[]
    for job in sorted(binding['jobs'],key=lambda j:(PHASES.index(j['phase']),j['source_ordinal'],j['record_index'])):
        records=binding['speech_records'] if job['speech'] else binding['nonspeech_records']
        profile=records[job['record_index']]['profile']
        folder=args.study/'records'/job['phase']/('source-%03d'%job['source_ordinal'])/('profile-%d'%profile)
        marker=folder/'complete-private.json'
        if not marker.exists():
            missing.append(dict(phase=job['phase'],source_ordinal=job['source_ordinal'],profile=profile));continue
        mark=json.loads(union.read(marker)); record=json.loads(union.read(folder/'record-private.json',mark['report_sha256']))
        assert mark['identity']==record['identity']==sha(canonical([binding['identity'],job]))
        assert all(record[k]==job[k] for k in ('phase','source_ordinal','record_index','speech','mode'))
        union.records[(job['phase'],job['source_ordinal'],profile)]=record
        count=union.add_record(record); observed[job['phase']]['records']+=1
        for key,value in count.items():observed[job['phase']][key]+=value
    chains=list(union.registry.values())
    small=[item for item in chains if item['entry']['file_bytes']<=FLASH_BYTES]
    stats=dict(schema='lpx-v5-adaptive-player-union-scope-estimate-v1',
        preliminary_unaudited=True,image_launch_allowed=False,producer_core_commit=binding['core_commit'],
        consumer_core_commit='5b4800f7',consumer_matches_v2_decoder_sources=True,
        expected_records=118,observed_complete_records=sum(row['records'] for row in observed.values()),
        missing_records=len(missing),all_six_workers_complete=all(row['status']=='complete' for row in workers),
        independent_audit_gate='pending',worker_snapshot=workers,by_phase=observed,
        automatic_changed_selection_views=sum(row['changed'] for row in observed.values()),
        unchanged_selection_views_skipped=sum(row['unchanged'] for row in observed.values()),
        no_automatic_selection_views=sum(row['no_automatic_selection'] for row in observed.values()),
        distinct_union_chains=len(chains),
        distinct_candidate_chains=sum('changed-automatic-selection' in item['roles'] for item in chains),
        distinct_rollback_chains=sum('declared-level-rollback' in item['roles'] for item in chains),
        distinct_comparisons=len(union.comparisons),logical_image_rows=2*len(chains),
        data_alone_no_fit_chains=len(chains)-len(small),data_alone_no_fit_rows=2*(len(chains)-len(small)),
        data_at_most_device_flash_chains=len(small),maximum_build_or_strict_reuse_rows=2*len(small),
        maximum_new_build_attempts=2*len(small),potential_full_playback_samples=2*sum(item['entry']['samples'] for item in small),
        maximum_chain_segments=max((len(item['entry']['segments']) for item in chains),default=0),
        new_fits=0,new_images=0,new_simulations=0,perceptual_adoption=False,
        scope='Observed completed-record snapshot only. Exact ordered-byte deduplication; device no-fit uses data alone. Final complete-worker and independent-audit gates are mandatory.')
    gate=None
    if args.final:
        stats['_consumer_inventory']=epoch.snapshot()
        gate=audit_gate(args,union,binding,workers,stats)
        stats.update(preliminary_unaudited=False,image_launch_allowed=True,independent_audit_gate='passed',
            scope='Complete fixed union after actual independent118-recordPASS, allsixworkerreceipts and accepted exact scope. Playback still requires full image admission; no fitting or quality adoption.')
    private=dict(schema='lpx-v5-adaptive-player-union-estimate-private-v1',image_launch_allowed=False,
        study_binding_sha256=sha(raw),study_identity=binding['identity'],input_files_sha256=union.inputs,
        source_inventory=epoch.snapshot(),chains=chains,comparisons=list(union.comparisons.values()),missing=missing,summary=stats)
    if args.final:
        private.update(schema='lpx-v5-adaptive-player-union-final-private-v1',image_launch_allowed=True,
            study_root=str(args.study),producer_core_commit=binding['core_commit'],consumer_root=str(epoch.root),
            admission_gate=gate,configuration=dict(irq_loads=[0,100],queue=256,prefill=192,assembly=True,flash_bytes=FLASH_BYTES),
            dispatcher_sources_sha256={str(p):sha(p.read_bytes()) for p in (THIS,HERE/'measure_union.py',HERE/'test_protocol.py',PROTOCOL,Path(sys.modules['admit'].__file__),HELPERS/'player_evidence.py')})
        for name,digest in binding['native_libraries_sha256'].items():union.read(args.study/'native'/name,digest)
    for path,digest in union.inputs.items():assert sha(Path(path).read_bytes())==digest
    epoch.modules['output_paths'].protect_outputs([*map(Path,union.inputs),THIS,PROTOCOL],[args.output,args.public_output])
    for target in (args.output,args.public_output):
        if target.exists():raise ValueError('Use fresh immutable estimate output names')
    epoch.save(args.output,private)
    args.public_output.parent.mkdir(parents=True,exist_ok=True)
    args.public_output.write_bytes(json.dumps(stats,indent=2,allow_nan=False).encode()+b'\n')
    print(json.dumps({key:stats[key] for key in ('observed_complete_records','missing_records','automatic_changed_selection_views',
        'distinct_union_chains','logical_image_rows','data_alone_no_fit_rows','maximum_new_build_attempts','potential_full_playback_samples')}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','study','output','public-output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--final',action='store_true')
    for name in ('audit','auditor-source','prepared','expect-scope'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--prior',action='append',type=Path,default=[])
    args=parser.parse_args()
    for name in ('source_root','study','output','public_output'):setattr(args,name,getattr(args,name).resolve())
    if args.final:
        if any(getattr(args,n) is None for n in ('audit','auditor_source','prepared','expect_scope')) or not args.prior:parser.error('Final preparation requires exact audit, auditor, player preparation, accepted scope and prior evidence')
        for name in ('audit','auditor_source','prepared','expect_scope'):setattr(args,name,getattr(args,name).resolve())
        args.prior=[path.resolve() for path in args.prior]
    try:estimate(args)
    except Exception as exc:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        failure=args.output.with_name('estimate-failure-private.json')
        failure.write_bytes(json.dumps(dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()),indent=2).encode()+b'\n')
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)))
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
