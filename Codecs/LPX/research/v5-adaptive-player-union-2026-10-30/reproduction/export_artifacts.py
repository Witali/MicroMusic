"""Read-only final player-union proof and anonymous cost projection."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import sys

THIS=Path(__file__).resolve()


def save(path,value):path.write_bytes(json.dumps(value,indent=2,allow_nan=False).encode()+b'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','handoff','campaign','package'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('source_root','handoff','campaign','package'):setattr(args,name,getattr(args,name).resolve())
    sys.path.insert(0,str(args.package/'reproduction'))
    from measure_union import context,guard,bound_streams,native_output,sha
    state=SimpleNamespace(source_root=args.source_root,handoff=args.handoff)
    epoch,proof,handoff,raw=context(state)
    load=lambda path:json.loads(path.read_bytes())
    summary,rows,private,source=[load(args.campaign/name) for name in ('summary.json','rows.json','results-private.json','source-runtime.json')]
    assert all(item['status']=='complete' for item in (summary,rows,private))
    assert summary==private['summary'] and private['handoff_sha256']==sha(raw)
    assert summary['unique_chains']==75 and summary['passed']==summary['rows']==len(rows['rows'])==len(private['rows'])==150
    assert summary['new_images']==132 and summary['reused_images']==18 and summary['verified_physical_samples']==6924372
    assert summary['no_fit']==summary['timing_or_output_failures']==summary['new_fits']==0 and not summary['perceptual_adoption']
    attempts=[]
    for shard in (0,1):
        attempt=load(args.campaign/'workers'/('shard-%d'%shard)/'attempt-private.json')
        assert attempt['status']=='complete' and attempt['handoff_sha256']==sha(raw)
        assert all(event['status']=='passed' for event in attempt['events'])
        assert not (args.campaign/'workers'/('shard-%d'%shard)/'failure-private.json').exists()
        attempts.append(attempt)
    assert sum(len(a['events']) for a in attempts)==150
    assert not list((args.campaign/'failures').glob('*-private.json'))
    assert source['source_inventory']==epoch.snapshot() and source['validation']==proof.validation
    for name,digest in handoff['dispatcher_sources_sha256'].items():assert sha(Path(name).read_bytes())==digest
    indexed={(row['chain'],row['extra_irq_cycles']):row for row in private['rows']}
    study=Path(handoff['study_root'])
    sessions=[epoch.modules['batch_decoder'].BatchSession('batch',prebuilt=study/'native'/name) for name in ('common.so','v5-only.so')]
    decoders=[session.__enter__() for session in sessions]
    try:
        for item in handoff['chains']:
            streams=bound_streams(item,epoch);expected=native_output(streams,item['entry'],epoch,decoders)
            for irq in (0,100):
                row=indexed[(item['id'],irq)]
                verified,folder=proof.reuse(row,streams,expected,irq)
                assert verified==row['verification']
                assert verified['cost']['complete_image'] and verified['cost']['embedded_streams_exact']
                assert row['flash_bytes']==verified['cost']['text_bytes']+verified['cost']['data_bytes']<=32768
                assert row['program_flash_bytes']==row['flash_bytes']-row['stream_bytes']
                assert row['static_sram_bytes']==verified['cost']['data_bytes']+verified['cost']['bss_bytes']
                report=row['report']
                assert report['produced']==report['played']==report['timer_ticks']==report['timer_events']==item['entry']['samples']
                assert report['underruns']==report['decoder_error']==report['observer_errors']==report['observer_exit_code']==report['queued_at_stop']==0
                assert report['eof']==report['stopped']==report['timer_started']==1 and report['stack_margin_all_bytes']>0
    finally:
        for session in sessions:session.__exit__()
    for hidden,visible in zip(private['rows'],rows['rows']):assert all(hidden[k]==v for k,v in visible.items())
    guard(epoch,handoff,raw,state,True)
    grouped=defaultdict(list)
    for comparison in summary['comparisons']:
        assert comparison['both_passed']
        for selection in comparison['selections']:
            grouped[(selection['phase'],selection['percent'],comparison['extra_irq_cycles'])].append(comparison)
    def distribution(values):
        growth=[-value['complete_flash_saved_bytes'] for value in values]
        program=[value['program_flash_change_bytes'] for value in values]
        return dict(views=len(values),full_flash_smaller=sum(g<0 for g in growth),same_full_flash=sum(g==0 for g in growth),
            full_flash_larger=sum(g>0 for g in growth),minimum_full_flash_growth_bytes=min(growth),maximum_full_flash_growth_bytes=max(growth),
            minimum_program_growth_bytes=min(program),maximum_program_growth_bytes=max(program))
    phase_caps=[dict(phase=phase,percent=percent,extra_irq_cycles=irq,**distribution(values))
        for (phase,percent,irq),values in sorted(grouped.items())]
    comparisons_by_irq={str(irq):distribution([c for c in summary['comparisons'] if c['extra_irq_cycles']==irq]) for irq in (0,100)}
    paired={}
    for comparison in summary['comparisons']:paired.setdefault(comparison['id'],{})[comparison['extra_irq_cycles']]=-comparison['complete_flash_saved_bytes']
    largest=max(rows['rows'],key=lambda r:r['flash_bytes'])
    cost_projection=dict(schema='lpx-v5-adaptive-player-union-cost-projection-v1',
        unique_comparison_pairs=len(paired),changed_cap_views=42,
        comparison_distribution_by_irq=comparisons_by_irq,phase_cap_view_distribution=phase_caps,
        paired_growth_equal_across_irqs=all(v[0]==v[100] for v in paired.values()),
        images=dict(minimum_full_flash_bytes=min(r['flash_bytes'] for r in rows['rows']),maximum_full_flash_bytes=max(r['flash_bytes'] for r in rows['rows']),
            minimum_program_flash_bytes=min(r['program_flash_bytes'] for r in rows['rows']),maximum_program_flash_bytes=max(r['program_flash_bytes'] for r in rows['rows']),
            minimum_static_sram_bytes=min(r['static_sram_bytes'] for r in rows['rows']),maximum_static_sram_bytes=max(r['static_sram_bytes'] for r in rows['rows']),
            minimum_observed_stack_margin_bytes=min(r['report']['stack_margin_all_bytes'] for r in rows['rows']),
            maximum_reset_segments=max(r['segments'] for r in rows['rows']),
            largest_image=dict(chain=largest['chain'],profile=largest['profile'],samples=largest['samples'],segments=largest['segments'],
                stream_bytes=largest['stream_bytes'],extra_irq_cycles=largest['extra_irq_cycles'],flash_bytes=largest['flash_bytes'])),
        physical_samples=dict(total=summary['verified_physical_samples'],
            new_images=sum(r['samples'] for r in rows['rows'] if r['newly_built_and_simulated']),
            proven_reuses=sum(r['samples'] for r in rows['rows'] if r['reused_frozen_image'])),
        new_fits=0,new_builds_or_simulations_during_export=0,perceptual_adoption=False,
        scope='Full-Flash growth is candidate minus same-level rollback. Phase/cap views overlap; source quality and audibility are not measured here.')
    for name in ('summary.json','rows.json','source-runtime.json'):
        target=args.package/name
        assert not target.exists() or target.read_bytes()==(args.campaign/name).read_bytes()
        shutil.copyfile(args.campaign/name,target)
    save(args.package/'cost-summary.json',cost_projection)
    target=args.package/'reproduction/export_artifacts.py'
    if target.resolve()!=THIS:shutil.copyfile(THIS,target)
    sources={str(Path(name).relative_to(args.package)) if Path(name).is_relative_to(args.package) else
        '../v5-adaptive-target-player-2026-10-30/reproduction/'+Path(name).name:digest
        for name,digest in handoff['dispatcher_sources_sha256'].items()}
    sources['reproduction/export_artifacts.py']=sha(target.read_bytes())
    save(args.package/'reproduction/sources.json',dict(schema='lpx-v5-adaptive-player-union-reproduction-v1',
        consumer_core_commit='5b4800f7',producer_core_commit=handoff['producer_core_commit'],sources=sources,
        scope='Exact pinned dispatcher/protocol/contracts and unchanged shared helpers, plus executed read-only exporter. No private asset bindings.'))
    save(args.package/'artifact-check.json',dict(schema='lpx-v5-adaptive-player-union-artifact-check-v1',status='passed',
        campaign_attempts=2,failed_attempts=0,chains=75,image_rows=150,new_images=132,strict_prior_reuses=18,
        complete_physical_pwm_samples_checked=6924372,changed_automatic_cap_views_covered=42,
        source_compiler_recipe_runtime_image_header_ordered_data_expected_pwm_eof_ticks_queue_stack_checked=True,
        native_common_v5_pcm_pwm_rechecked=True,actual_data_metadata_program_flash_charged=True,
        full_length_reset_chains_preserved=True,new_fits=0,new_avr_builds_during_export=0,new_avr_simulations_during_export=0,
        perceptual_adoption=False,private_media_or_firmware_fingerprints_exported=False))
    print(json.dumps(dict(status='passed artifact proof and anonymous export',image_rows=150,new_images=132,strict_reuses=18)))


if __name__=='__main__':main()
