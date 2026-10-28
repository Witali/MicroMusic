"""Replay the immutable111+5 diagnostic matrix with complete host statistics.

Private study manifests/media stay in ignored storage. Public outputs contain
anonymous numeric rows and source/toolchain/host-validator provenance only.
Historical durations are never compared with current full-chain averages.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,time
from pathlib import Path
from benchmark_speech_flash import canonical,source_hashes,srcdir,validation_provenance,environment
from measure_speech_firmware import simulate,checked_output
from speech_compact import unpack,decode_model
from standard_metrics import pwm_duties

def sha(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.writing')
 temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n');temporary.replace(path)

def prepare(study):
    """Resolve the historical job set without changing its stress choices."""
    study=Path(study);timing_path=study/'timing/results.json';costs_path=study/'firmware/all-costs.json';selection_path=study/'selection/results.json'
    timing=load(timing_path);costs=load(costs_path);selection=load(selection_path)
    if timing.get('status')!='complete' or timing['normal_unique_chains']!=111 or timing['stress_unique_chains']!=5:
        raise ValueError('Expected the frozen111normal+5stress inventory')
    if selection['costs_sha256']!=sha(costs_path.read_bytes()):raise ValueError('Historical stream inventory changed')
    lookup={entry['key']:entry for group in costs['groups'] for entry in group['entries']}
    rows=sorted(timing['reports'],key=lambda row:(row['extra_irq_cycles'],row['key']))
    if len(rows)!=116 or sum(row['extra_irq_cycles']==0 for row in rows)!=111 or sum(row['extra_irq_cycles']==100 for row in rows)!=5:
        raise ValueError('Historical matrix differs from111normal+5stress')
    jobs=[];unique=set();model_cache={}
    for ordinal,row in enumerate(rows,1):
        chain=row['key'];irq=row['extra_irq_cycles'];identity=(chain,irq)
        if identity in unique:raise ValueError('Duplicate diagnostic image')
        unique.add(identity);entry=lookup[chain];parts=[];blobs=[]
        for segment in entry['segments']:
            blob=Path(segment['path']).read_bytes();digest=sha(blob);n=unpack(blob)[0]
            if digest!=segment['stream_sha256'] or len(blob)!=segment['file_bytes'] or n!=segment['samples']:
                raise ValueError('Current ordered stream files differ from frozen inventory')
            if digest not in model_cache:model_cache[digest]=pwm_duties(decode_model(blob)).tobytes()
            parts.append(model_cache[digest]);blobs.append(blob)
        report=row['report'];hashes=[sha(blob) for blob in blobs]
        if hashes!=report['cost']['stream_sha256'] or sha(canonical(hashes))!=chain:
            raise ValueError('Frozen image does not bind current ordered streams')
        expected=b''.join(parts);frozen=study/'timing'/('irq-'+str(irq))/chain/'valid.pcm8'
        if expected!=frozen.read_bytes() or sha(expected)!=report['pwm_sha256']:
            raise ValueError('Independent-model/frozen complete PWM mismatch')
        jobs.append({'id':f'diagnostic-{ordinal:03d}','key':chain,'irq':irq,'streams':blobs,
                     'expected_pwm_sha256':sha(expected),'samples':len(expected),'segments':len(blobs)})
    inputs={str(path.relative_to(study)):sha(path.read_bytes()) for path in (timing_path,costs_path,selection_path)}
    return jobs,inputs


def run(study,source,output,avr_bin,runner,lib=None,wsl=None,workers=3,limit=None):
    if type(workers) is not int or not 1<=workers<=3:raise ValueError('workers must be1..3')
    if limit is not None and (type(limit) is not int or not 1<=limit<=116):raise ValueError('limit must be1..116')
    start=time.perf_counter();src=srcdir(source);source_inventory=source_hashes(src);output=checked_output(output)
    jobs,input_hashes=prepare(study);selected=jobs if limit is None else jobs[:limit]
    validator=validation_provenance(runner,lib,wsl,sources=(Path(__file__),));rows=[];private=[]
    toolchain=environment(src,avr_bin,True)
    timing_fields=('produced','played','timer_ticks','underruns','decoder_error','decode_calls',
        'decode_wall_cycles_total','decode_wall_cycles_max','decode_wall_cycles_max_40','decode_wall_cycles_max_80',
        'decode_wall_cycles_max_160','stack_margin_bytes','min_queue_before_producer_eos',
        'decode_timing_samples','decode_timing_complete','decode_timing_statistics_scope')
    cost_fields=('samples','segments','stream_bytes','flash_bytes','program_flash_bytes','static_sram_bytes')
    def job(item):
        folder=output/'images'/('irq-'+str(item['irq']))/item['key']
        verified=simulate(item['streams'],folder,avr_bin,runner,lib=lib,wsl=wsl,source=src,irq=item['irq'],validator_sources=(Path(__file__),))
        if (verified['pwm_sha256']!=item['expected_pwm_sha256'] or verified['cost']['samples']!=item['samples']
                or not verified['decode_timing_complete'] or verified['decode_timing_samples']!=item['samples']
                or verified['historical_runner']):raise AssertionError('Incomplete/current full-duration validation')
        if verified['cost']['environment']['dependencies']!=toolchain['dependencies']:
            raise ValueError('AVR toolchain changed during diagnostic matrix')
        if verified['cost']['flash_bytes']>32768:raise AssertionError('Target Flash exceeded')
        row={'id':item['id'],'extra_irq_cycles':item['irq'],**{key:verified[key] for key in timing_fields},
             **{key:verified['cost'][key] for key in cost_fields},'complete_model_and_frozen_pwm_exact':True}
        return row,{'id':item['id'],'key':item['key'],'report':verified}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(job,item) for item in selected]):
            row,record=future.result();rows.append(row);private.append(record)
            if source_hashes(src)!=source_inventory:raise ValueError('Source changed during diagnostic matrix')
            save(output/'results-private.json',{'status':'running','source_sha256':source_inventory,'inputs_sha256':input_hashes,'reports':private})
            print(json.dumps({'verified':len(rows),'requested':len(selected),'irq':row['extra_irq_cycles'],'underruns':row['underruns']}),flush=True)
    if source_hashes(src)!=source_inventory or validation_provenance(runner,lib,wsl,sources=(Path(__file__),))!=validator:
        raise ValueError('Source or host validator changed during diagnostic matrix')
    for name,expected in input_hashes.items():
        if sha((Path(study)/name).read_bytes())!=expected:raise ValueError('Frozen inventory changed during matrix')
    if environment(src,avr_bin,True)!=toolchain:raise ValueError('AVR build environment changed during matrix')
    rows.sort(key=lambda row:row['id']);normal=[row for row in rows if row['extra_irq_cycles']==0];samples=sum(row['decode_timing_samples'] for row in normal)
    sample=private[0]['report']['cost'] if private else None
    summary={'schema':'lpx-v5-full-diagnostic-runtime-v1','status':'complete' if len(rows)==116 else 'partial',
        'normal_images':len(normal),'stress_images':len(rows)-len(normal),'expected_normal_images':111,'expected_stress_images':5,
        'all_full_pwm_exact':True,'zero_underruns_all':all(row['underruns']==0 for row in rows),
        'all_decode_duration_coverage_complete':all(row['decode_timing_complete'] for row in rows),
        'normal_profiled_samples':samples,'normal_mean_decode_wall_cycles':sum(row['decode_wall_cycles_total'] for row in normal)/samples if samples else None,
        'minimum_stack_margin_bytes':min(row['stack_margin_bytes'] for row in rows),
        'minimum_queue_before_producer_eos':min(row['min_queue_before_producer_eos'] for row in rows),
        'source_sha256':source_inventory,'source_fingerprint':sha(canonical(source_inventory)),
        'compiler':sample['environment']['compiler'],'compiler_options':sample['compiler_options'],
        'toolchain_dependencies':sample['environment']['dependencies'],'validator_provenance':validator,
        'historical_input_manifests_sha256':input_hashes,'driver_sha256':sha(Path(__file__).read_bytes()),
        'physical_board_measured':False,'scope':'Diagnostic harness, same immutable111+5 jobs; full duration coverage. Historical capped averages are not used.','elapsed_seconds':time.perf_counter()-start}
    save(output/'public/summary.json',summary);save(output/'public/rows.json',{'schema':'lpx-v5-full-diagnostic-runtime-rows-v1','rows':rows})
    save(output/'results-private.json',{'status':summary['status'],'source_sha256':source_inventory,'inputs_sha256':input_hashes,'reports':private})
    print(json.dumps({key:summary[key] for key in ('status','normal_images','stress_images','normal_profiled_samples','normal_mean_decode_wall_cycles','elapsed_seconds')}),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','source','output','avr-bin','runner'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--lib',type=Path);parser.add_argument('--wsl');parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--limit',type=int,help='Explicit partial smoke scope, never marked full admission')
    run(**vars(parser.parse_args()))
if __name__=='__main__':main()
