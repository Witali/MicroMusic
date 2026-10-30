"""Reopen retention-extension proofs and publish only anonymous measurements."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

THIS = Path(__file__).resolve()
GENERIC = THIS.parents[2]/'v5-adaptive-player-union-2026-10-30/reproduction'
sys.path.insert(0,str(GENERIC))
from measure_union import (context,guard,bound_streams,native_output,
                           verify_failed_image,sha,FLASH_BYTES)


def load(path):
    return json.loads(path.read_bytes())


def save(path,value):
    path.write_bytes(json.dumps(value,indent=2,allow_nan=False).encode()+b'\n')


def distribution(values):
    measured = [value for value in values if value['both_passed']]
    growth = [-value['complete_flash_saved_bytes'] for value in measured]
    program = [value['program_flash_change_bytes'] for value in measured]
    return dict(views=len(values),both_passed=len(measured),not_both_admitted=len(values)-len(measured),
        full_flash_smaller=sum(value<0 for value in growth),same_full_flash=sum(value==0 for value in growth),
        full_flash_larger=sum(value>0 for value in growth),
        full_flash_growth_bytes=sorted(growth),program_flash_growth_bytes=sorted(program))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','handoff','campaign','package'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    for name in ('source_root','handoff','campaign','package'):
        setattr(args,name,getattr(args,name).resolve())
    state = SimpleNamespace(source_root=args.source_root,handoff=args.handoff)
    epoch,proof,handoff,raw = context(state)
    assert handoff['retention_gate']['independent_ordered_byte_postcheck']=='passed'
    summary,rows,private,source = [load(args.campaign/name) for name in
        ('summary.json','rows.json','results-private.json','source-runtime.json')]
    assert all(value['status']=='complete' for value in (summary,rows,private))
    assert summary==private['summary'] and private['handoff_sha256']==sha(raw)
    assert summary['unique_chains']==len(handoff['chains'])
    assert summary['rows']==len(rows['rows'])==len(private['rows'])==handoff['summary']['logical_image_rows']
    assert summary['new_fits']==0 and not summary['perceptual_adoption']
    assert source['source_inventory']==epoch.snapshot() and source['validation']==proof.validation
    events = 0
    for shard in (0,1):
        worker = args.campaign/'workers'/('shard-%d'%shard)
        attempt = load(worker/'attempt-private.json')
        assert attempt['status']=='complete' and attempt['handoff_sha256']==sha(raw)
        assert all(event['status'] in ('passed','no-fit-data-alone','no-fit-linked-flash','timing-or-output-failed') for event in attempt['events'])
        assert not (worker/'failure-private.json').exists()
        events += len(attempt['events'])
    assert events==summary['rows'] and not list((args.campaign/'failures').glob('*-private.json'))
    indexed = {(row['chain'],row['extra_irq_cycles']):row for row in private['rows']}
    study = Path(handoff['study_root'])
    sessions = [epoch.modules['batch_decoder'].BatchSession('batch',prebuilt=study/'native'/name)
                for name in ('common.so','v5-only.so')]
    decoders = [session.__enter__() for session in sessions]
    try:
        for item in handoff['chains']:
            streams = bound_streams(item,epoch)
            expected = native_output(streams,item['entry'],epoch,decoders) if item['entry']['file_bytes']<=FLASH_BYTES else None
            for irq in (0,100):
                row = indexed[(item['id'],irq)]
                assert row['stream_sha256']==[sha(blob) for blob in streams]
                if row['passed']:
                    verified,_ = proof.reuse(row,streams,expected,irq)
                    assert verified==row['verification']
                    cost,report = verified['cost'],row['report']
                    assert cost['complete_image'] and cost['embedded_streams_exact']
                    assert row['flash_bytes']==cost['text_bytes']+cost['data_bytes']<=FLASH_BYTES
                    assert row['program_flash_bytes']==row['flash_bytes']-row['stream_bytes']
                    assert row['static_sram_bytes']==cost['data_bytes']+cost['bss_bytes']
                    assert report['produced']==report['played']==report['timer_ticks']==report['timer_events']==item['entry']['samples']
                    assert report['underruns']==report['decoder_error']==report['observer_errors']==report['observer_exit_code']==report['queued_at_stop']==0
                    assert report['eof']==report['stopped']==report['timer_started']==1
                    assert report['stack_margin_all_bytes']>0
                elif row['verification'] is not None:
                    verify_failed_image(proof,row,streams,expected)
                elif row['status']=='no-fit-data-alone':
                    assert item['entry']['file_bytes']>FLASH_BYTES
                else:
                    # The aggregate has bound and classified the exact retained
                    # linker log; reopen its bytes again without a build.
                    assert row['status']=='no-fit-linked-flash'
                    assert sha((Path(row['output'])/'compile.stderr.log').read_bytes())==row['compile_log_sha256']
    finally:
        for session in sessions:
            session.__exit__()
    for hidden,visible in zip(private['rows'],rows['rows']):
        assert all(hidden[name]==value for name,value in visible.items())
    guard(epoch,handoff,raw,state,True)
    by_view = defaultdict(list)
    for comparison in summary['comparisons']:
        for selection in comparison['selections']:
            by_view[(selection['phase'],selection['percent'],comparison['extra_irq_cycles'])].append(comparison)
    selected = {item['id'] for item in handoff['chains'] if 'changed-automatic-selection' in item['roles']}
    rollback = {item['id'] for item in handoff['chains'] if 'declared-level-rollback' in item['roles']}
    def role_counts(identifiers):
        values = [row for row in rows['rows'] if row['chain'] in identifiers]
        return dict(unique_chains=len(identifiers),rows=len(values),passed=sum(row['passed'] for row in values),
            new_images=sum(row['newly_built_and_simulated'] for row in values),
            strict_reuses=sum(row['reused_frozen_image'] for row in values),
            statuses=dict(Counter(row['status'] for row in values)))
    admitted = [row for row in rows['rows'] if row['passed']]
    largest = max(admitted,key=lambda row:row['flash_bytes']) if admitted else None
    projection = dict(schema='lpx-v5-retention-player-cost-projection-v1',
        canonical_selector_commit=handoff['retention_gate']['selector_commit'],
        complete_replay_records=118,cap_views=354,new_selection_cap_views=handoff['summary']['automatic_changed_selection_views'],
        selected=role_counts(selected),rollback=role_counts(rollback),role_overlap_chains=len(selected & rollback),
        comparison_distribution_by_irq={str(irq):distribution([c for c in summary['comparisons'] if c['extra_irq_cycles']==irq]) for irq in (0,100)},
        phase_cap_view_distribution=[dict(phase=phase,percent=percent,extra_irq_cycles=irq,**distribution(values))
            for (phase,percent,irq),values in sorted(by_view.items())],
        largest_admitted_image=None if largest is None else {name:largest[name] for name in
            ('chain','profile','samples','segments','stream_bytes','extra_irq_cycles','flash_bytes','program_flash_bytes')},
        minimum_static_sram_bytes=min((row['static_sram_bytes'] for row in admitted),default=None),
        maximum_static_sram_bytes=max((row['static_sram_bytes'] for row in admitted),default=None),
        minimum_observed_stack_margin_bytes=min((row['report']['stack_margin_all_bytes'] for row in admitted),default=None),
        verified_physical_samples=summary['verified_physical_samples'],new_fits=0,
        new_builds_or_simulations_during_export=0,perceptual_adoption=False,
        scope='Actual full Flash versus exact declared-level rollback; views overlap. Data-cap selection is distinct from hardware admission. No quality metrics or subjective adoption measured here.')
    for name in ('summary.json','rows.json','source-runtime.json'):
        target = args.package/name
        assert not target.exists() or target.read_bytes()==(args.campaign/name).read_bytes()
        shutil.copyfile(args.campaign/name,target)
    save(args.package/'cost-summary.json',projection)
    save(args.package/'final-scope.json',handoff['summary'])
    sources = {Path(os.path.relpath(name,args.package)).as_posix():digest
               for name,digest in handoff['dispatcher_sources_sha256'].items()}
    sources[Path(os.path.relpath(THIS,args.package)).as_posix()] = sha(THIS.read_bytes())
    save(args.package/'reproduction/sources.json',dict(schema='lpx-v5-retention-player-sources-v1',sources=sources,
        consumer_core_commit='5b4800f7',producer_primitives_commit=handoff['producer_core_commit'],
        canonical_selector_commit=handoff['retention_gate']['selector_commit'],private_asset_bindings_exported=False))
    save(args.package/'artifact-check.json',dict(schema='lpx-v5-retention-player-artifact-check-v1',status='passed',
        image_rows=summary['rows'],passed_images=summary['passed'],new_images=summary['new_images'],strict_reuses=summary['reused_images'],
        device_no_fit=summary['no_fit'],timing_or_output_failures=summary['timing_or_output_failures'],
        admitted_images_source_recipe_runtime_ordered_data_pwm_eof_queue_ticks_stack_checked=True,
        admitted_chains_model_common_v5_pcm_pwm_rechecked=True,full_length_chains_preserved=True,
        no_fit_rows_make_no_playback_admission_claim=True,
        complete_flash_includes_data_metadata_and_program=True,new_fits=0,new_avr_builds_during_export=0,
        new_avr_simulations_during_export=0,perceptual_adoption=False,private_asset_fingerprints_exported=False))
    print(json.dumps(dict(status='passed artifact proof and anonymous export',rows=summary['rows'],
        passed=summary['passed'],new_images=summary['new_images'],strict_reuses=summary['reused_images'],device_no_fit=summary['no_fit'])),flush=True)


if __name__=='__main__':
    main()
