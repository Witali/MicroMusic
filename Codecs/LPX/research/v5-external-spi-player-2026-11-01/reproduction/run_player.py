"""Finite SPI player bind, bounded parity, two long shards and proof aggregate."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parent))
from spi_player import (ROOT,PACKAGE,HOST,SHARED,rom,bench,load,save,sha,require,source_inventory,
                        simulate,checked_image,reopen_spi,reopen_rom)

LONG_SHARDS=4


def long_partition(identifiers,shard):
    require(type(shard) is int and 0<=shard<LONG_SHARDS,'Unsupported fixed long shard')
    return {identifier for index,identifier in enumerate(sorted(identifiers)) if index%LONG_SHARDS==shard}


def plan_rows(cases):
    chains={chain['id']:chain for chain in cases['chains']}
    require(len(chains)==8 and Counter(chain['kind'] for chain in chains.values())=={'long':6,'short':2},
            'The fixed case population changed')
    require(Counter(chain['profile'] for chain in chains.values())=={4:4,6:4},'Profiles changed')
    require(Counter((chain['kind'],chain['profile']) for chain in chains.values())==
            {('long',4):3,('long',6):3,('short',4):1,('short',6):1},'Per-profile case allocation changed')
    wanted=set()
    for chain in chains.values():
        long=chain['kind']=='long'
        require(chain['samples']==(3786111 if long else 160) and len(chain['sizes'])==(60 if long else 1),
                'Whole chain/reset coverage changed')
        for storage in (('spi',) if long else ('spi','rom')):
            for assembly in ((True,) if long else (False,True)):
                for irq in (0,100):wanted.add((chain['id'],storage,assembly,irq))
    actual={(row['chain_id'],row['storage'],row['assembly'],row['extra_irq_cycles']) for row in cases['rows']}
    require(actual==wanted and len(cases['rows'])==len(actual)==28
            and len({row['id'] for row in cases['rows']})==28
            and all(type(row['assembly']) is bool for row in cases['rows']),'The accepted28-image plan changed')
    return chains


def guard(handoff,raw,args,inputs=False):
    require(args.handoff.read_bytes()==raw and source_inventory()==handoff['source_inventory'],'Bound source/handoff changed')
    require(sha(Path(handoff['spi_observer']).read_bytes())==handoff['spi_observer_sha256']
            and sha(Path(handoff['rom_observer']).read_bytes())==handoff['rom_observer_sha256'],'A bound observer changed')
    if inputs:
        for name,digest in handoff['input_files_sha256'].items():
            require(sha(Path(name).read_bytes())==digest,'A bound case/reference/dependency changed')


def context(args):
    raw=args.handoff.read_bytes();handoff=load(args.handoff)
    require(handoff['schema']=='lpx-external-spi-player-handoff-private-v1' and handoff['status']=='bound',
            'Require a fixed final SPI handoff')
    require(handoff['long_shards']==LONG_SHARDS,'Bound partition count changed')
    cases=load(handoff['cases_path']);chains=plan_rows(cases)
    guard(handoff,raw,args,True)
    return handoff,raw,cases,chains


def reopen_record(h,chain,row,record):
    folder=Path(record['output'])
    if row['storage']=='spi':verified=reopen_spi(chain,row,folder,Path(h['avr_bin']),Path(h['spi_observer']))
    else:verified=reopen_rom(chain,row,folder,Path(h['avr_bin']),Path(h['rom_observer']),Path(h['lib']),h['wsl'],record)
    require(bench.canonical(verified)==bench.canonical(record['verification']),
            'Reopened proof differs from the bound worker receipt')
    return verified


def bind(args):
    require(not args.handoff.exists(),'Preserve an existing immutable handoff')
    cases=load(args.cases);chains=plan_rows(cases)
    require(cases['schema']=='lpx-external-spi-cases-private-v1' and cases['status']=='prepared','Case preparation did not pass')
    pins={str(args.cases):sha(args.cases.read_bytes())}
    complete_path=args.cases.parent/'complete-private.json';complete=load(complete_path)
    require(complete['status']=='complete' and complete['handoff_sha256']==sha(args.cases.read_bytes())
            and complete['chains']==8 and complete['long_chains']==6 and complete['synthetic_chains']==2
            and complete['rows']==28 and complete['source_input_output_guards_passed']
            and complete['new_fits']==complete['new_search_calls']==complete['avr_builds']==complete['simulation_jobs']==0,
            'Native case completion receipt is incomplete')
    pins[str(complete_path)]=sha(complete_path.read_bytes())
    for name,digest in cases['reference_source_sha256'].items():
        path=ROOT/name;require(sha(path.read_bytes())==digest,'Native reference source changed');pins[str(path)]=digest
    for name,digest in cases['input_files_sha256'].items():
        require(sha(Path(name).read_bytes())==digest,'A used case input changed');pins[name]=digest
    for chain in chains.values():
        for key,digest_key in (('external_image_path','external_image_sha256'),('expected_pwm_path','expected_pwm_sha256')):
            path=Path(chain[key]);require(sha(path.read_bytes())==chain[digest_key],'Prepared image/reference changed')
            pins[str(path)]=chain[digest_key]
        require(Path(chain['external_image_path']).stat().st_size==16777216
                and Path(chain['expected_pwm_path']).stat().st_size==chain['samples'],'Prepared image/reference length differs')
        require(sum(chain['sizes'])==chain['stream_bytes'] and len(chain['payload_bytes_by_segment'])==len(chain['sizes'])
                and sum(chain['payload_bytes_by_segment'])==chain['expected_payload_bytes']<=chain['stream_bytes'],
                'Requested-byte counts differ from full stored streams')
        for part in chain['segments']:
            path=Path(part['path']);require(sha(path.read_bytes())==part['stream_sha256'],'Prepared reset bytes changed')
            pins[str(path)]=part['stream_sha256']
    receipt=load(args.spi_observer.parent/'receipt-private.json')
    require(receipt['status']=='built-not-player-admitted' and not receipt['installed_library_modified']
            and receipt['binary_sha256']==sha(args.spi_observer.read_bytes()),'Require the exact isolated SPI observer')
    timing=load(args.spi_observer.parent/'timing-test/receipt-private.json')
    require(timing['status']=='PASS' and timing['test'][-1]['divisors']==8 and timing['test'][-1]['fast_byte_cycles']==16,
            'Actual eight-divisor timing test did not pass')
    bridge_log=args.spi_observer.parent/'bridge-test.stdout.log'
    import json
    bridge=[json.loads(line) for line in bridge_log.read_text().splitlines() if line.startswith('{')]
    require(bridge==[dict(status='PASS',completed_bytes=13,vendor_metadata_fields=37,explicit_seeks=2,player_images=0)],
            'Actual GPIO/CS/repeated-byte/seek bridge test did not pass')
    for record in (receipt,timing):
        for name,digest in record['source_sha256'].items():
            require(sha(Path(name).read_bytes())==digest,'Observer/unit inputs changed');pins[name]=digest
    for path in (args.spi_observer.parent/'receipt-private.json',args.spi_observer.parent/'timing-test/receipt-private.json',bridge_log):
        pins[str(path)]=sha(path.read_bytes())
    rom_build=load(args.rom_observer.parent/'observer-build.json')
    require(rom_build['binary_sha256']==sha(args.rom_observer.read_bytes()),'ROM observer build proof changed')
    for name,digest in rom_build['source_sha256'].items():
        require(sha(Path(name).read_bytes())==digest,'ROM observer source/dependency changed');pins[name]=digest
    pins[str(args.rom_observer.parent/'observer-build.json')]=sha((args.rom_observer.parent/'observer-build.json').read_bytes())
    vendor=load(SHARED/'PROVENANCE.json')
    for name,digest in vendor['installed_headers_sha256'].items():
        path=args.avr_bin.parent/'avr/include/avr'/name
        require(sha(path.read_bytes())==digest,'Installed AVR vendor-header provenance changed');pins[str(path)]=digest
    pins[str(SHARED/'PROVENANCE.json')]=sha((SHARED/'PROVENANCE.json').read_bytes())
    h=dict(schema='lpx-external-spi-player-handoff-private-v1',status='bound',cases_path=str(args.cases),
        source_inventory=source_inventory(),input_files_sha256=pins,avr_bin=str(args.avr_bin),
        spi_observer=str(args.spi_observer),spi_observer_sha256=sha(args.spi_observer.read_bytes()),
        rom_observer=str(args.rom_observer),rom_observer_sha256=sha(args.rom_observer.read_bytes()),lib=str(args.lib),wsl=args.wsl,
        exact_rows=28,long_rows=12,bounded_spi_rows=8,matched_rom_rows=8,
        long_shards=LONG_SHARDS,
        configuration=dict(cpu_hz=16000000,audio_hz=8000,sck_hz=8000000,queue=256,prefill=192,irq_loads=[0,100]),
        new_searches=0,physical_board_claim=False,c_8khz_sustainability_claim=False)
    save(args.handoff,h)
    print('{"status":"bound","rows":28,"long_rows":12,"bounded_rows":16,"new_images":0}',flush=True)


def worker(args):
    h,raw,cases,chains=context(args)
    if args.action=='bounded':rows=[row for row in cases['rows'] if chains[row['chain_id']]['kind']=='short'];name='bounded'
    else:
        bounded=load(args.output/'workers/bounded/results-private.json')
        reopened=load(args.output/'workers/bounded/artifact-check-private.json')
        require(bounded['status']=='complete' and bounded['handoff_sha256']==sha(raw)
                and len(bounded['rows'])==16 and all(row['passed'] for row in bounded['rows'])
                and reopened['status']=='passed' and reopened['handoff_sha256']==sha(raw) and reopened['rows']==16,
                'All bounded C/ASM/SPI/ROM rows must pass before long runs')
        long_ids=sorted(chain['id'] for chain in chains.values() if chain['kind']=='long')
        chosen=long_partition(long_ids,args.shard)
        rows=[row for row in cases['rows'] if row['chain_id'] in chosen];name='long-shard-%d'%args.shard
    folder=args.output/'workers'/name
    require(not folder.exists(),'Inspect the existing worker attempt before recovery')
    attempt=dict(status='running',handoff_sha256=sha(raw),events=[],new_searches=0)
    save(folder/'attempt-private.json',attempt)
    began=time.perf_counter();results=[]
    try:
        for row in rows:
            chain=chains[row['chain_id']];image=args.output/'images'/row['id']
            require(not image.exists(),'Inspect a previous fixed image attempt')
            guard(h,raw,args)
            event=dict(id=row['id'],status='running',started_unix_ns=time.time_ns());attempt['events'].append(event)
            save(folder/'attempt-private.json',attempt)
            start=time.perf_counter()
            if row['storage']=='spi':
                verified=simulate(chain,row,image,Path(h['avr_bin']),Path(h['spi_observer']),Path(h['lib']),h['wsl'])
            else:
                streams=[Path(part['path']).read_bytes() for part in chain['segments']]
                original_save=rom.save
                rom.save=save # Same JSON/checkpoint semantics, bounded Windows5/32 replace retry.
                try:
                    verified=rom.simulate(streams,image,Path(h['avr_bin']),Path(h['rom_observer']),assembly=row['assembly'],
                        queue=256,prefill=192,irq=row['extra_irq_cycles'],lib=Path(h['lib']),wsl=h['wsl'],
                        expected_pwm=Path(chain['expected_pwm_path']).read_bytes(),require_valid=False)
                finally:rom.save=original_save
            cost,report=verified['cost'],verified['report'];elapsed=time.perf_counter()-start
            result={**row,'kind':chain['kind'],'profile':chain['profile'],'samples':chain['samples'],
                'segments':len(chain['sizes']),'stored_stream_bytes':chain['stream_bytes'],
                'passed':bool(verified['passed'] and cost['flash_bytes']<=32768),
                'flash_bytes':cost['flash_bytes'],'program_flash_bytes':cost['program_flash_bytes'],
                'static_sram_bytes':cost['static_sram_bytes'],'wall_seconds':elapsed,'report':report,
                'output':str(image),'verification':verified}
            results.append(result);event.update(status='passed' if result['passed'] else 'failed',ended_unix_ns=time.time_ns())
            save(folder/'attempt-private.json',attempt)
            save(folder/'results-private.json',dict(status='running',handoff_sha256=sha(raw),rows=results))
            print(__import__('json').dumps({key:result[key] for key in ('id','passed','flash_bytes','static_sram_bytes','wall_seconds')}),flush=True)
            require(result['passed'],'A fixed player image failed; do not launch alternate/repeated images')
        guard(h,raw,args,True)
        if args.action=='bounded':
            # Reopen the saved JSON representation: native build results can
            # contain tuple ranges, while persisted proof records use lists.
            checkpoint=load(folder/'results-private.json')
            require(checkpoint['status']=='running' and checkpoint['handoff_sha256']==sha(raw)
                    and checkpoint['rows']==json.loads(json.dumps(results,allow_nan=False)),
                    'Saved bounded results differ from the completed image results')
            results=checkpoint['rows']
            by_id={row['id']:row for row in rows}
            for record in results:reopen_record(h,chains[record['chain_id']],by_id[record['id']],record)
            save(folder/'artifact-check-private.json',dict(status='passed',handoff_sha256=sha(raw),rows=16,
                 both_backends_and_storage_recipes_reopened=True,new_builds_or_simulations=0))
        summary=dict(status='complete',rows=len(results),passed=sum(row['passed'] for row in results),
                     wall_seconds=time.perf_counter()-began,new_searches=0)
        save(folder/'results-private.json',dict(status='complete',handoff_sha256=sha(raw),rows=results,summary=summary))
        attempt.update(status='complete');save(folder/'attempt-private.json',attempt)
        print(__import__('json').dumps(summary),flush=True)
    except Exception as exc:
        # Preserve a final failed atomic write and write the failure before
        # touching that journal again. A completed image is never repeated here.
        save(folder/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        attempt.update(status='failed',exception_type=type(exc).__name__)
        try:save(folder/'attempt-private.json',attempt)
        except (OSError,ValueError):pass # failure receipt and pending .writing remain authoritative.
        print('{"status":"failed","worker":"'+name+'"}',flush=True);return 1
    return 0


def aggregate(args):
    h,raw,cases,chains=context(args)
    joined=[]
    long_ids=[chain['id'] for chain in chains.values() if chain['kind']=='long']
    workers=[('bounded',16)]+[('long-shard-%d'%shard,2*len(long_partition(long_ids,shard))) for shard in range(LONG_SHARDS)]
    for name,expected in workers:
        folder=args.output/'workers'/name
        result=load(folder/'results-private.json');attempt=load(folder/'attempt-private.json')
        require(result['status']=='complete' and result['handoff_sha256']==sha(raw)
                and attempt['status']=='complete' and attempt['handoff_sha256']==sha(raw)
                and len(result['rows'])==len(attempt['events'])==expected
                and all(event['status']=='passed' for event in attempt['events']),
                'Every fixed worker must be complete without an unresolved attempt')
        joined.extend(result['rows'])
    index={row['id']:row for row in joined}
    require(len(index)==len(joined)==28,'Worker rows overlap or are incomplete')
    public=[]
    for row in cases['rows']:
        record=index[row['id']];chain=chains[row['chain_id']];folder=Path(record['output'])
        require(all(record[name]==value for name,value in row.items()) and record['passed'],'A fixed row changed')
        reopen_record(h,chain,row,record)
        public.append({name:value for name,value in record.items() if name not in ('output','verification')})
    matched=[]
    for chain in chains.values():
        if chain['kind']!='short':continue
        for assembly in (False,True):
            for irq in (0,100):
                rows=[row for row in public if row['chain_id']==chain['id'] and row['assembly']==assembly and row['extra_irq_cycles']==irq]
                require(len(rows)==2,'A matched short ROM/SPI pair is missing')
                spi=next(row for row in rows if row['storage']=='spi');rom_row=next(row for row in rows if row['storage']=='rom')
                matched.append(dict(profile=chain['profile'],assembly=assembly,extra_irq_cycles=irq,
                    spi_full_program_flash_bytes=spi['program_flash_bytes'],rom_program_excluding_stream_bytes=rom_row['program_flash_bytes'],
                    full_program_flash_growth_bytes=spi['program_flash_bytes']-rom_row['program_flash_bytes'],
                    spi_full_flash_bytes=spi['flash_bytes'],rom_full_flash_bytes=rom_row['flash_bytes'],
                    spi_sram_bytes=spi['static_sram_bytes'],rom_sram_bytes=rom_row['static_sram_bytes'],both_outputs_exact=True))
    guard(h,raw,args,True)
    summary=dict(schema='lpx-external-spi-player-results-v1',status='complete',rows=28,passed=28,
        long_spi_rows=12,bounded_spi_rows=8,matched_short_rom_rows=8,
        physical_samples=sum(row['samples'] for row in public),
        long_physical_samples=sum(row['samples'] for row in public if row['kind']=='long'),
        minimum_stack_margin_bytes=min(row['report']['stack_margin_all_bytes'] for row in public),
        underruns=sum(row['report']['underruns'] for row in public),matched_program_costs=matched,
        new_searches=0,repeated_player_attempts=0,physical_board_claim=False,c_8khz_sustainability_claim=False,
        perceptual_adoption=False,scope='Exact finite full long ASM SPI playback and bounded C/ASM/SPI/ROM parity; source/body/model timing limitations retained.')
    save(args.output/'results-private.json',dict(status='complete',handoff_sha256=sha(raw),rows=joined,summary=summary))
    save(args.output/'rows.json',dict(schema='lpx-external-spi-player-rows-v1',status='complete',rows=public))
    save(args.output/'summary.json',summary)
    print(__import__('json').dumps({key:summary[key] for key in ('status','rows','passed','long_physical_samples','underruns')}),flush=True)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('bind','bounded','long','aggregate'))
    parser.add_argument('--handoff',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--shard',type=int,choices=tuple(range(LONG_SHARDS)))
    for name in ('cases','avr-bin','spi-observer','rom-observer','lib'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--wsl');args=parser.parse_args()
    for name in ('handoff','output','cases','avr_bin','spi_observer','rom_observer','lib'):
        value=getattr(args,name)
        if value is not None:setattr(args,name,value.resolve())
    if args.action=='bind' and any(getattr(args,name) is None for name in ('cases','avr_bin','spi_observer','rom_observer','lib')):
        parser.error('Bind requires all final case/toolchain/observer inputs')
    if args.action!='bind' and args.output is None:parser.error('A worker requires a fixed campaign output')
    if (args.action=='long')!=(args.shard is not None):parser.error('Only long takes exactly one parity shard')
    if args.action=='bind':bind(args);return 0
    if args.action=='aggregate':return aggregate(args)
    return worker(args)


if __name__=='__main__':raise SystemExit(main())
