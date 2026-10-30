"""Measure the final audited V2 exact-chain union in isolated parity shards."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import traceback

THIS=Path(__file__).resolve(); HERE=THIS.parent
sys.path.insert(0,str(HERE))
from prepare_union import Epoch, Union, FLASH_BYTES, PHASES, sha
from player_evidence import PlayerEvidence


def load(path):return json.loads(Path(path).read_bytes())


def guard(epoch,handoff,raw,args,all_inputs=False):
    assert args.handoff.read_bytes()==raw and epoch.snapshot()==handoff['source_inventory']
    for name,digest in handoff['dispatcher_sources_sha256'].items():assert sha(Path(name).read_bytes())==digest
    if all_inputs:
        for name,digest in handoff['input_files_sha256'].items():assert sha(Path(name).read_bytes())==digest


def context(args):
    raw=args.handoff.read_bytes(); handoff=json.loads(raw)
    assert handoff['schema']=='lpx-v5-adaptive-player-union-final-private-v1' and handoff['image_launch_allowed']
    assert handoff['summary']['all_six_workers_complete'] and handoff['summary']['independent_audit_gate']=='passed'
    assert handoff['summary']['observed_complete_records']==118 and not handoff['summary']['missing_records']
    assert handoff['configuration']==dict(irq_loads=[0,100],queue=256,prefill=192,assembly=True,flash_bytes=FLASH_BYTES)
    for source in (THIS,Path(sys.modules['prepare_union'].__file__).resolve(),
                   Path(sys.modules['player_evidence'].__file__).resolve(),Path(sys.modules['admit'].__file__).resolve()):
        assert str(source) in handoff['dispatcher_sources_sha256']
        assert sha(source.read_bytes())==handoff['dispatcher_sources_sha256'][str(source)]
    epoch=Epoch(args.source_root)
    assert Path(handoff['consumer_root']).resolve()==epoch.root
    audit=load(handoff['admission_gate']['private_audit_path'])
    assert audit['status']=='passed' and audit['binding_sha256']==handoff['study_binding_sha256']
    assert audit['completed_records']==audit['expected_records']==118 and audit['all_final_worker_receipts_verified']
    prepared=load(handoff['admission_gate']['prepared_path'])
    assert prepared['source_inventory']==epoch.snapshot()
    proof=PlayerEvidence(epoch,prepared)
    guard(epoch,handoff,raw,args,True)
    return epoch,proof,handoff,raw


def prior_index(handoff):
    index={}
    for directory in handoff['admission_gate']['prior_paths']:
        receipt=load(Path(directory)/'results-private.json'); assert receipt['status']=='complete'
        for row in receipt['rows']:
            if not row.get('passed') or row.get('verification') is None:continue
            identifiers=row.get('stream_sha256',row.get('streams_sha256'))
            assert isinstance(identifiers,list) and identifiers
            key=(tuple(identifiers),row['extra_irq_cycles'])
            if key not in index:index[key]=row
    return index


def bound_streams(item,epoch):
    parser=Union(epoch.modules['speech_compact'].unpack)
    entry=item['entry']
    adapted={**entry,'stream_bytes':entry['file_bytes']}
    return list(parser.chain(adapted,entry['profile']))


def native_output(streams,entry,epoch,decoders):
    import numpy as np
    parts=[]
    for blob in streams:
        pcm=epoch.modules['speech_compact'].decode_model(blob)
        expected=epoch.modules['standard_metrics'].pwm_duties(pcm)
        for decoder in decoders:
            np.testing.assert_array_equal(decoder.decode_one_s16(blob,len(pcm)),pcm)
            np.testing.assert_array_equal(decoder.decode_one(blob,len(pcm)),expected)
        parts.append(pcm)
    pcm=np.concatenate(parts); pwm=epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes()
    assert len(pcm)==entry['samples'] and sha(pcm.astype('<i2').tobytes())==entry['pcm16_sha256'] and sha(pwm)==entry['pwm_sha256']
    return pwm


def verify_failed_image(proof,row,streams,expected):
    """Bind an observed failed image without pretending it is reusable/pass."""
    folder=Path(row['output']); cached=load(folder/'cost.json'); verified=load(folder/'verification.json')
    cost=verified['cost']; build,image,flags=proof.recipe(streams,row['extra_irq_cycles'])
    assert cached['fingerprint']==image and cached['proof_fingerprint']==proof.proof
    assert cached['cost_sha256']==sha(proof.bench.canonical(cost)) and cached['cost']==cost==row['verification']['cost']
    assert cost['environment']==proof.env and cost['build_fingerprint']==build and cost['compiler_options']==flags
    proof.verify_recipe(cost,streams,row['extra_irq_cycles'])
    for name,key in (('player.elf','image_sha256'),('program.bin','binary_sha256'),('player.hex','hex_sha256')):assert proof.bench.digest(folder/name)==cost[key]
    proof.player.checked_image(folder,proof.avr,streams,256)
    assert verified['validation_provenance']==proof.validation
    assert verified['fingerprint']==sha(proof.bench.canonical([proof.validation,cost['image_sha256'],proof.bench.digest(folder/'observer.txt'),sha(expected),0]))
    actual=(folder/'valid.pcm8').read_bytes(); report=load(folder/'observer.json')
    assert verified['report_sha256']==proof.bench.digest(folder/'observer.json') and verified['pwm_sha256']==sha(actual)
    assert report==verified['report']==row['report']
    assert verified['passed']==proof.player.validate(report,actual,expected)
    assert row['passed']==(verified['passed'] and cost['flash_bytes']<=FLASH_BYTES)
    assert not row['passed']


def run(args):
    began=time.perf_counter(); epoch,proof,handoff,raw=context(args)
    output=epoch.output(args.output); folder=output/'workers'/('shard-%d'%args.shard)
    attempt_path=folder/'attempt-private.json'
    if attempt_path.exists():raise ValueError('Inspect existing attempt before an explicit audited resume')
    items=[item for index,item in enumerate(handoff['chains']) if index%2==args.shard]
    index=prior_index(handoff)
    inputs=[args.handoff,*map(Path,handoff['input_files_sha256']),*map(Path,handoff['dispatcher_sources_sha256'])]
    epoch.modules['output_paths'].protect_outputs(inputs,[folder/name for name in ('rows.json','results-private.json','summary.json','attempt-private.json')])
    attempt=dict(status='running',handoff_sha256=sha(raw),shard=args.shard,started_unix_ns=time.time_ns(),events=[],new_fits=0)
    epoch.save(attempt_path,attempt)
    study=Path(handoff['study_root']); native=[]; rows=[]; private=[]
    sessions=[epoch.modules['batch_decoder'].BatchSession('batch',prebuilt=study/'native'/name) for name in ('common.so','v5-only.so')]
    try:
        native=[session.__enter__() for session in sessions]
        for item in items:
            entry=item['entry']; streams=bound_streams(item,epoch)
            fits_data=entry['file_bytes']<=FLASH_BYTES
            expected=native_output(streams,entry,epoch,native) if fits_data else None
            for irq in (0,100):
                guard(epoch,handoff,raw,args)
                assert bound_streams(item,epoch)==streams
                event=dict(chain=item['id'],extra_irq_cycles=irq,status='running',started_unix_ns=time.time_ns())
                attempt['events'].append(event); epoch.save(attempt_path,attempt)
                key=(tuple(sha(blob) for blob in streams),irq); old=index.get(key)
                image=output/'images'/item['id']/('irq-%d'%irq)
                result=None; reused=False; status=None; compile_log_sha=None
                if not fits_data:status='no-fit-data-alone'
                elif old is not None:
                    result,image=proof.reuse(old,streams,expected,irq); reused=True
                else:
                    if image.exists():raise ValueError('Unexpected image cache in a fresh campaign')
                    epoch.player.guard(image,inputs)
                    try:
                        result=epoch.player.simulate(streams,image,proof.avr,proof.runner,source=epoch.active,
                            queue=256,prefill=192,irq=irq,assembly=True,lib=proof.lib,wsl=proof.wsl,
                            expected_pwm=expected,require_valid=False)
                    except RuntimeError:
                        log=image/'compile.stderr.log'; text=log.read_text(errors='replace') if log.is_file() else ''
                        if re.search(r'(?:region.*text.*overflowed|will not fit in region.*text)',text,re.I):
                            status='no-fit-linked-flash'; compile_log_sha=sha(log.read_bytes())
                        else:raise
                row=dict(chain=item['id'],roles=item['roles'],profile=entry['profile'],samples=entry['samples'],
                    segments=len(streams),stream_bytes=entry['file_bytes'],extra_irq_cycles=irq,
                    model_common_compact_pcm_pwm_exact=fits_data,reused_frozen_image=reused,
                    newly_built_and_simulated=result is not None and not reused,status=status,passed=False,
                    quality_measured_here=False,perceptual_adoption=False)
                if result is not None:
                    cost,report=result['cost'],result['report']; proof.verify_recipe(cost,streams,irq)
                    assert result['validation_provenance']==proof.validation and cost['environment']==proof.env
                    actual=(image/'valid.pcm8').read_bytes(); within=cost['flash_bytes']<=FLASH_BYTES
                    passed=result['passed'] and within
                    row.update(status='passed' if passed else ('no-fit-linked-flash' if not within else 'timing-or-output-failed'),
                        passed=passed,flash_bytes=cost['flash_bytes'],program_flash_bytes=cost['program_flash_bytes'],
                        static_sram_bytes=cost['static_sram_bytes'],data_bytes=cost['data_bytes'],bss_bytes=cost['bss_bytes'],
                        report=report,physical_pwm_exact=actual==expected and report['underruns']==0 and report['timer_ticks']==entry['samples'])
                rows.append(row)
                private.append({**row,'output':str(image),'stream_sha256':[sha(blob) for blob in streams],
                    'pcm16_sha256':entry['pcm16_sha256'],'pwm_sha256':entry['pwm_sha256'],
                    'verification':result,'compile_log_sha256':compile_log_sha})
                event.update(status=row['status'],passed=row['passed'],reused=reused,ended_unix_ns=time.time_ns())
                epoch.save(attempt_path,attempt)
                epoch.save(folder/'rows.json',dict(status='running',rows=rows))
                epoch.save(folder/'results-private.json',dict(status='running',handoff_sha256=sha(raw),shard=args.shard,rows=private))
                print(json.dumps({key:row[key] for key in ('chain','extra_irq_cycles','status','reused_frozen_image','newly_built_and_simulated')}),flush=True)
        guard(epoch,handoff,raw,args,True)
        fresh=PlayerEvidence(epoch,load(handoff['admission_gate']['prepared_path']))
        assert fresh.env==proof.env and fresh.validation==proof.validation
        summary=dict(schema='lpx-v5-adaptive-player-union-worker-v1',status='complete',shard=args.shard,
            chains=len(items),rows=len(rows),passed=sum(row['passed'] for row in rows),
            newly_built_and_simulated=sum(row['newly_built_and_simulated'] for row in rows),
            reused_frozen_images=sum(row['reused_frozen_image'] for row in rows),
            no_fit=sum(row['status'].startswith('no-fit') for row in rows),
            timing_or_output_failures=sum(row['status']=='timing-or-output-failed' for row in rows),
            new_fits=0,worker_wall_seconds=time.perf_counter()-began)
        epoch.save(folder/'rows.json',dict(status='complete',rows=rows))
        epoch.save(folder/'results-private.json',dict(status='complete',handoff_sha256=sha(raw),shard=args.shard,rows=private,summary=summary))
        epoch.save(folder/'summary.json',summary)
        attempt.update(status='complete',ended_unix_ns=time.time_ns()); epoch.save(attempt_path,attempt)
        print(json.dumps(summary),flush=True)
    except Exception as exc:
        attempt.update(status='failed',exception_type=type(exc).__name__,ended_unix_ns=time.time_ns()); epoch.save(attempt_path,attempt)
        epoch.save(folder/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',shard=args.shard,exception_type=type(exc).__name__)),flush=True)
        return 1
    finally:
        for session in sessions:session.__exit__()
    return 0


def aggregate(args):
    epoch,proof,handoff,raw=context(args); output=epoch.output(args.output)
    joined=[]; workers=[]
    for shard in (0,1):
        folder=output/'workers'/('shard-%d'%shard); result=load(folder/'results-private.json')
        assert result['status']=='complete' and result['shard']==shard and result['handoff_sha256']==sha(raw)
        assert load(folder/'attempt-private.json')['status']=='complete'
        workers.append(result['summary']); joined.extend(result['rows'])
    indexed={(row['chain'],row['extra_irq_cycles']):row for row in joined}
    assert len(indexed)==len(joined)==handoff['summary']['logical_image_rows']
    public=[]; private=[]
    for item in handoff['chains']:
        streams=bound_streams(item,epoch); entry=item['entry']; expected=None
        if entry['file_bytes']<=FLASH_BYTES:
            import numpy as np
            pcm=np.concatenate([epoch.modules['speech_compact'].decode_model(blob) for blob in streams])
            expected=epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes()
            assert sha(pcm.astype('<i2').tobytes())==entry['pcm16_sha256'] and sha(expected)==entry['pwm_sha256']
        for irq in (0,100):
            row=indexed[(item['id'],irq)]
            assert row['stream_sha256']==[sha(blob) for blob in streams] and row['stream_bytes']==sum(map(len,streams))
            if row['verification'] is not None:
                if row['passed']:proof.reuse(row,streams,expected,irq)
                else:verify_failed_image(proof,row,streams,expected)
            elif row['status']=='no-fit-data-alone':assert entry['file_bytes']>FLASH_BYTES
            else:
                assert row['status']=='no-fit-linked-flash'
                log=Path(row['output'])/'compile.stderr.log'; assert sha(log.read_bytes())==row['compile_log_sha256']
                assert re.search(r'(?:region.*text.*overflowed|will not fit in region.*text)',log.read_text(errors='replace'),re.I)
            private.append(row)
            public.append({name:value for name,value in row.items() if name not in ('output','stream_sha256','pcm16_sha256','pwm_sha256','verification','compile_log_sha256')})
    comparisons=[]
    for comparison in handoff['comparisons']:
        for irq in (0,100):
            before=indexed[(comparison['rollback_chain'],irq)]; after=indexed[(comparison['candidate_chain'],irq)]
            row={**comparison,'extra_irq_cycles':irq,'both_passed':before['passed'] and after['passed'],
                'rollback_stream_bytes':before['stream_bytes'],'candidate_stream_bytes':after['stream_bytes'],
                'data_saved_bytes':before['stream_bytes']-after['stream_bytes'],
                'complete_flash_saved_bytes':None if 'flash_bytes' not in before or 'flash_bytes' not in after else before['flash_bytes']-after['flash_bytes'],
                'program_flash_change_bytes':None if 'program_flash_bytes' not in before or 'program_flash_bytes' not in after else after['program_flash_bytes']-before['program_flash_bytes']}
            comparisons.append(row)
    guard(epoch,handoff,raw,args,True)
    summary=dict(schema='lpx-v5-adaptive-player-union-admission-v1',status='complete',unique_chains=len(handoff['chains']),
        changed_selected_cap_views=handoff['summary']['automatic_changed_selection_views'],unchanged_views_skipped=handoff['summary']['unchanged_selection_views_skipped'],
        rows=len(public),passed=sum(row['passed'] for row in public),
        new_images=sum(row['newly_built_and_simulated'] for row in public),reused_images=sum(row['reused_frozen_image'] for row in public),
        no_fit=sum(row['status'].startswith('no-fit') for row in public),timing_or_output_failures=sum(row['status']=='timing-or-output-failed' for row in public),
        verified_physical_samples=sum(row['samples'] for row in public if row['passed']),workers=workers,comparisons=comparisons,
        new_fits=0,perceptual_adoption=False,scope='Audited changed automatic whole selections versus exact same-level rollbacks; actual complete images/IRQs. No raw-ineligible admission, refitting, trimming, quality-policy or original-level gain claim.')
    source=dict(schema='lpx-v5-adaptive-player-union-source-v1',producer_core_commit=handoff['producer_core_commit'],consumer_core_commit='5b4800f7',
        source_inventory=epoch.snapshot(),decoder_source_sha256=proof.env['source_sha256'],compiler=proof.env['compiler'],dependencies=proof.env['dependencies'],
        compile_source_sha256=proof.env['compile_source_sha256'],harness_sha256=proof.env['harness_sha256'],validation=proof.validation,
        dispatcher_sources_sha256={Path(name).name:digest for name,digest in handoff['dispatcher_sources_sha256'].items()},
        compiler_options_by_irq={str(irq):proof.recipe(bound_streams(handoff['chains'][0],epoch),irq)[2] for irq in (0,100)},
        queue=256,prefill=192,explicit_asm=True,irq_loads=[0,100],private_asset_bindings_exported=False)
    epoch.save(output/'rows.json',dict(schema='lpx-v5-adaptive-player-union-rows-v1',status='complete',rows=public))
    epoch.save(output/'results-private.json',dict(status='complete',handoff_sha256=sha(raw),rows=private,summary=summary))
    epoch.save(output/'summary.json',summary); epoch.save(output/'source-runtime.json',source)
    print(json.dumps({key:summary[key] for key in ('status','rows','passed','new_images','reused_images','no_fit','timing_or_output_failures','verified_physical_samples')}),flush=True)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=('run','aggregate'))
    for name in ('source-root','handoff','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--shard',type=int,choices=(0,1)); args=parser.parse_args()
    if (args.action=='run')!=(args.shard is not None):parser.error('Run requires one parity shard; aggregate takes none')
    for name in ('source_root','handoff','output'):setattr(args,name,getattr(args,name).resolve())
    try:return run(args) if args.action=='run' else aggregate(args)
    except Exception as exc:
        folder=args.output/'failures'; folder.mkdir(parents=True,exist_ok=True)
        prefix=args.action+'-'+str(args.shard)+'-failure-'
        number=len(list(folder.glob(prefix+'*-private.json')))
        target=folder/(prefix+'%03d-private.json'%number)
        target.write_bytes(json.dumps(dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()),indent=2).encode()+b'\n')
        print(json.dumps(dict(status='failed',action=args.action,shard=args.shard,exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
