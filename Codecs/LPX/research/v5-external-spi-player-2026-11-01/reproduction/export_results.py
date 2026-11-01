"""Read-only source/receipt projection of the completed28-image SPI evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_player as run

THIS=Path(__file__).resolve()
PACKAGE=THIS.parents[1]


def output(path,value):
    raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    if path.exists() and path.read_bytes()!=raw:raise ValueError('Preserve a different previous public projection')
    path.write_bytes(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('handoff','campaign','original-campaign'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-ref',default='8c680fcf')
    parser.add_argument('--repair-ref',default='9a896163')
    args=parser.parse_args()
    for name in ('handoff','campaign','original_campaign'):setattr(args,name,getattr(args,name).resolve())
    state=__import__('types').SimpleNamespace(handoff=args.handoff,output=args.campaign)
    h,raw,cases,chains=run.context(state)
    summary=run.load(args.campaign/'summary.json');rows=run.load(args.campaign/'rows.json')
    private=run.load(args.campaign/'results-private.json')
    run.require(summary['status']==private['status']==rows['status']=='complete'
        and private['handoff_sha256']==run.sha(raw) and private['summary']==summary
        and summary['rows']==summary['passed']==28 and summary['underruns']==0
        and summary['long_physical_samples']==45433332,'Full finite image admission is incomplete')
    indexed={row['id']:row for row in private['rows']}
    for row in cases['rows']:
        record=indexed[row['id']]
        run.reopen_record(h,chains[row['chain_id']],row,record)
    run.require(len(rows['rows'])==28 and all(all(indexed[row['id']][name]==value for name,value in row.items())
                for row in rows['rows']),'Public rows differ from exact private proof')
    admission=run.load(args.campaign/'workers/bounded/artifact-check-private.json')
    mapping=admission['admission'];admit_source=Path(mapping['source_file'])
    run.require(mapping['role']=='derived-read-only-admission' and mapping['new_builds']==mapping['new_simulations']==0
        and run.sha(admit_source.read_bytes())==mapping['source_sha256'],'Bounded admission source changed')
    for name,digest in mapping['original_receipts_sha256'].items():
        run.require(run.sha(Path(name).read_bytes())==digest,'Original administrative failure/proof changed')
    original=run.load(args.original_campaign/'workers/bounded/attempt-private.json')
    run.require(original['status']=='failed' and len(original['events'])==16
                and all(event['status']=='passed' for event in original['events']),'Original end-stage failure was relabelled')
    source_ref=subprocess.check_output(['git','rev-parse',args.source_ref],text=True).strip()
    repair_ref=subprocess.check_output(['git','rev-parse',args.repair_ref],text=True).strip()
    for name,digest in h['source_inventory'].items():
        blob=subprocess.check_output(['git','show',source_ref+':'+name])
        run.require(run.sha(blob)==digest,'The immutable public source ref differs from actual measured bytes')
    run.guard(h,raw,state,True)
    long=[row for row in rows['rows'] if row['kind']=='long']
    short=[row for row in rows['rows'] if row['kind']=='short']
    images=[]
    for identifier in sorted(chains):
        chain=chains[identifier]
        values=[row for row in rows['rows'] if row['chain_id']==identifier and row['storage']=='spi']
        images.append(dict(chain_id=identifier,kind=chain['kind'],profile=chain['profile'],samples=chain['samples'],
            reset_segments=len(chain['sizes']),stored_stream_bytes=chain['stream_bytes'],
            actual_requested_payload_bytes=chain['expected_payload_bytes'],
            valid_unread_stored_suffix_bytes=chain['stream_bytes']-chain['expected_payload_bytes'],
            external_capacity_bytes=16777216,metadata_flash_bytes=6*len(chain['sizes']),
            flash_bytes_by_backend_irq=[dict(assembly=row['assembly'],extra_irq_cycles=row['extra_irq_cycles'],
                flash_bytes=row['flash_bytes'],static_sram_bytes=row['static_sram_bytes']) for row in values]))
    costs=dict(schema='lpx-external-spi-cost-summary-v1',chains=images,matched_short_program_costs=summary['matched_program_costs'],
        long_rows=12,minimum_long_program_flash_bytes=min(row['flash_bytes'] for row in long),
        maximum_long_program_flash_bytes=max(row['flash_bytes'] for row in long),
        long_static_sram_bytes=sorted({row['static_sram_bytes'] for row in long}),
        minimum_long_stack_margin_bytes=min(row['report']['stack_margin_all_bytes'] for row in long),
        minimum_long_wall_seconds=min(row['wall_seconds'] for row in long),maximum_long_wall_seconds=max(row['wall_seconds'] for row in long),
        source_and_data_separate=True,long_rom_embedding='device-no-fit-data-alone; linked program size unavailable',
        physical_samples=dict(long=45433332,bounded_spi=sum(row['samples'] for row in short if row['storage']=='spi'),
            matched_short_rom=sum(row['samples'] for row in short if row['storage']=='rom')),
        maximum_dispatch_lateness_cycles=max(row['report']['spi']['dispatch_lateness_max_cycles'] for row in long),
        maximum_spi_software_gap_cycles=max(row['report']['spi']['software_gap_max_cycles'] for row in long),
        completions_during_audio_irq=sum(row['report']['spi']['completions_during_audio_irq'] for row in long),
        new_searches=0,physical_board_claim=False,c_8khz_sustainability_claim=False)
    for name in ('summary.json','rows.json'):
        destination=PACKAGE/name
        raw_bytes=(args.campaign/name).read_bytes()
        run.require(not destination.exists() or destination.read_bytes()==raw_bytes,'Preserve a different prior projection')
        destination.write_bytes(raw_bytes)
    output(PACKAGE/'cost-summary.json',costs)
    output(PACKAGE/'artifact-check.json',dict(schema='lpx-external-spi-artifact-check-v1',status='passed',case_configuration_rows=28,
        new_image_builds=28,simulations=28,repeated_case_configuration_attempts=0,
        distinct_elf_byte_contents=len({row['verification']['cost']['image_sha256'] for row in private['rows']}),
        distinct_program_binary_contents=len({row['verification']['cost']['binary_sha256'] for row in private['rows']}),
        long_images=12,bounded_spi_images=8,matched_rom_images=8,
        all_source_recipe_data_metadata_runtime_output_proofs_reopened=True,zero_underruns=True,
        requested_payload_matches_native_reference=True,stored_tails_preserved=True,source_handoff_preserved=True,
        original_bounded_administrative_failure_preserved=True,derived_bounded_gate='strict read-only persisted JSON admission',
        new_builds_or_simulations_during_admission_or_export=0,private_assets_or_fingerprints_exported=False,
        physical_board_claim=False,c_8khz_sustainability_claim=False,perceptual_adoption=False))
    sources=dict(schema='lpx-external-spi-executed-sources-v1',equivalent_immutable_source_ref=source_ref,
        measured_source_inventory_sha256=h['source_inventory'],source_files_checked=len(h['source_inventory']),
        source_only_fresh_reproduction_repair_ref=repair_ref,
        repair_scope='Reload persisted JSON before the bounded gate; no measured MCU source/flags change or repeated simulation',
        bounded_admission_source=dict(path=admit_source.relative_to(run.ROOT).as_posix(),sha256=mapping['source_sha256']),
        exporter=dict(path=THIS.relative_to(run.ROOT).as_posix(),sha256=run.sha(THIS.read_bytes())),
        archive_rule='Resolve each measured path from the immutable Git ref; canonical run_player.py later contains the separately labelled source-only repair',
        private_asset_bindings_exported=False)
    output(PACKAGE/'reproduction/sources.json',sources)
    print(json.dumps(dict(status='passed exact artifact export',case_configuration_rows=28,long_physical_samples=45433332,
        new_images_or_simulations=0,immutable_source_files_checked=len(h['source_inventory']))),flush=True)


if __name__=='__main__':main()
