"""Frozen hypothetical complete-byte study; no new format, audio, or quality metric."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from fractions import Fraction
import hashlib
import importlib.metadata
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from dataclasses import asdict
import speech_compact as compact
from speech_parameter_costs import METHODS,chain_cost,inspect_stream
from speech_parameter_histograms import parameter_histograms,parameter_codes
from benchmark_speech_flash import source_hashes,validation_sources
from measure_speech_firmware import checked_output
from output_paths import protect_outputs

sha=lambda b:hashlib.sha256(b).hexdigest()
canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(path):return json.loads(Path(path).read_text())
def save(path,value):
    path=Path(path);checked_output(path)
    if path.is_symlink() or path.exists() and path.stat().st_nlink>1:raise ValueError('Output aliases another file')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


ASSUMPTIONS={'source_format':'actual existing v5 bytes; untouched fields are not repacked',
    'proposed_header_bytes':23,'additional_method_selector_bytes_per_segment':1,
    'first_tuple_bits_per_segment':15,'field_widths':[5,7,3],
    'repeat':'one flag per selected later field; changed fields retain full absolute width',
    'rice':'zigzag delta q<8 costs q+1+k; q>=8 is eight zero bits then full absolute field',
    'masks_repeat':[1,2,3,4,5,6,7],'masks_rice':[5,7],'rice_common_k':[0,1,2],
    'history':'reset only per segment; update every stored tuple, including unused lag and tail',
    'alignment':'continuous LSB packing within segment, exact independent final byte padding',
    'nomination':'tuning baseline and expanded100 only; positive aggregate savings in both, minimum repeat field count then best worst-source fractional saving; best Rice is separate higher-complexity point',
    'fallback':'optional per-segment min(v5,new) is a data-only envelope; dual decoder cost is not free',
    'flash':'saved complete stream bytes are optimistic added-decoder/table/layout allowance only; no linked firmware saving is measured',
    'quality':'no STOI, music quality, perceived gain or implemented new-decoder exactness claim'}


def source_binding():
    return {'decoder_sources':source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'),
        'host_sources':validation_sources((Path(__file__),)),'python':sys.version,
        'packages':{n:importlib.metadata.version(n) for n in ('numpy','numba','scipy','pystoi','soundfile')},
        'assumptions':ASSUMPTIONS,'methods':[asdict(m) for m in METHODS]}


def inputs(main_path,expanded_paths,nonspeech_path):
    main_raw=Path(main_path).read_bytes();main=json.loads(main_raw);non_raw=Path(nonspeech_path).read_bytes();non=json.loads(non_raw)
    if len(main['records'])!=98 or len({r['private_case_id'] for r in main['records']})!=49:raise ValueError('Expected49case main manifest')
    if len(non['records'])!=264 or len({r['private_case_id'] for r in non['records']})!=132:raise ValueError('Expected132case robustness manifest')
    if main['source_sha256']!=non['source_sha256'] or main['source_sha256']!=source_binding()['decoder_sources']:
        raise ValueError('Frozen decoder source mismatch')
    lookup={r['id']:r for r in main['records']};result=[];case_ids={};private_files={str(Path(main_path).resolve()):sha(main_raw),str(Path(nonspeech_path).resolve()):sha(non_raw)}
    def add(family,domain,row,segments,bytes_expected):
        key=(domain,row['private_case_id'])
        if key not in case_ids:case_ids[key]=f'{domain}-case-{sum(k[0]==domain for k in case_ids)+1:03d}'
        result.append({'family':family,'domain':domain,'case':case_ids[key],'profile':row['profile'],'split':row['split'],
            'cohort':row['cohort'],'samples':row['samples'],'segments':segments,'expected_segment_geometry':row['segments'],
            'expected_bytes':bytes_expected,'private_case_id':row['private_case_id']})
    for row in main['records']:add('baseline-v2','main',row,row['segments'],row['baseline_bytes'])
    seen=set()
    for path in expanded_paths:
        raw=Path(path).read_bytes();data=json.loads(raw);private_files[str(Path(path).resolve())]=sha(raw)
        if data['status']!='complete' or data['manifest_sha256']!=sha(main_raw) or data['source_sha256']!=main['source_sha256']:
            raise ValueError('Expanded100 receipt is incomplete or stale')
        for record in data['records']:
            identity=record['id']
            if identity in seen or identity not in lookup:raise ValueError('Duplicate or unknown expanded record')
            seen.add(identity);row=lookup[identity]
            if record['profile']!=row['profile'] or record['split']!=row['split']:raise ValueError('Expanded profile/split changed')
            budget=next(b for b in record['budgets'] if b['percent']==100);selected=budget['selected']
            if selected is None or selected['stream_bytes']>budget['cap'] or not selected['conservative_floors_passed']:
                raise ValueError('Expected selected expanded100 original-floor stream')
            add('expanded100','main',row,selected['segments'],selected['stream_bytes'])
    if len(seen)!=98:raise ValueError('Missing expanded100 profile groups')
    for row in non['records']:add('non-speech-baseline-v1','robustness',row,row['segments'],row['baseline_bytes'])
    if len(result)!=460:raise ValueError('Expected460 source/profile groups')
    for i,row in enumerate(result):row['id']=f'cost-{i+1:03d}'
    return result,private_files


def cost_summary(rows):
    old=sum(r['current_file_bytes'] for r in rows);new=sum(r['proposed_file_bytes'] for r in rows);saved=[r['whole_stream_saved_bytes'] for r in rows]
    return {'records':len(rows),'original_total_bytes':old,'proposed_total_bytes':new,'saved_total_bytes':old-new,
        'saved_fraction':float(Fraction(old-new,old)) if old else None,
        'saved_bytes_min_median_max':[min(saved),statistics.median(saved),max(saved)],
        'positive_zero_negative_records':[sum(v>0 for v in saved),sum(v==0 for v in saved),sum(v<0 for v in saved)],
        'fallback_data_only_total_upper_bound_bytes':sum(r['fallback_data_only_upper_bound_bytes'] for r in rows),
        'all_segment_sizes_within_rom_api':all(r['all_segment_sizes_within_rom_api'] for r in rows),
        'field_absolute_escape_counts':{field:sum(r['field_absolute_escapes'][field] for r in rows) for field in ('scale','lag','gain_code')}}


def nominate(rows):
    candidates=[]
    for method in METHODS:
        by_source={family:cost_summary([r for r in rows if r['family']==family and r['split']=='tuning' and r['method']['name']==method.name])
            for family in ('baseline-v2','expanded100')}
        eligible=all(v['records']==40 and v['saved_total_bytes']>0 and v['all_segment_sizes_within_rom_api'] for v in by_source.values())
        score=min(Fraction(v['saved_total_bytes'],v['original_total_bytes']) for v in by_source.values())
        candidates.append({'method':method,'sources':by_source,'eligible':eligible,'score':score})
    repeats=[r for r in candidates if r['eligible'] and r['method'].kind=='repeat']
    rice=[r for r in candidates if r['eligible'] and r['method'].kind=='rice']
    minimal=min(repeats,key=lambda r:(r['method'].mask.bit_count(),-r['score'],r['method'].selector)) if repeats else None
    advanced=min(rice,key=lambda r:(-r['score'],r['method'].mask.bit_count(),r['method'].selector)) if rice else None
    def point(row):return None if row is None else {'method':asdict(row['method']),'worst_source_saved_fraction':float(row['score']),'tuning_sources':row['sources']}
    return {'minimal_repeat':point(minimal),'higher_complexity_rice':point(advanced),
        'chosen_from_tuning_only':True,'frozen_before_heldout_costs':True,'rule':ASSUMPTIONS['nomination'],
        'tuning_candidates':[{'method':asdict(r['method']),'eligible':r['eligible'],'worst_source_saved_fraction':float(r['score']),'sources':r['sources']} for r in candidates]}


def run(main_path,expanded_paths,nonspeech_path,output):
    output=checked_output(output);records,private_inputs=inputs(main_path,expanded_paths,nonspeech_path);binding=source_binding()
    protect_outputs([Path(p) for p in private_inputs]+[Path(__file__)]+[Path(s['path']) for r in records for s in r['segments']],
        [output/name for name in ('results-private.json','nomination-lock-private.json','summary.json','rows.json','histograms.json','source-runtime.json','nomination.json')])
    started=time.perf_counter();cpu=time.process_time();inspections={};blobs_seen={};cost_rows=[];private_records=[];hist_groups=defaultdict(list)
    group_unused=defaultdict(lambda:Counter());stream_files={}
    training=[r for r in records if r['family'] in ('baseline-v2','expanded100') and r['split']=='tuning']
    rest=[r for r in records if r not in training];ordered=training+rest;nomination=None
    for ordinal,row in enumerate(ordered,1):
        blobs=[];infos=[];offset=0
        if len(row['segments'])!=len(row['expected_segment_geometry']):raise ValueError('Reset count changed')
        for segment,geometry in zip(row['segments'],row['expected_segment_geometry']):
            path=Path(segment['path']);blob=path.read_bytes();digest=sha(blob)
            if digest!=segment['stream_sha256'] or len(blob)!=segment['file_bytes']:raise ValueError('Current encoded source changed')
            absolute=str(path.resolve())
            if absolute in stream_files and stream_files[absolute]!=digest:raise ValueError('Source path has conflicting identities')
            stream_files[absolute]=digest
            if digest not in inspections:inspections[digest]=inspect_stream(blob);blobs_seen[digest]=blob
            info=inspections[digest]
            if info['profile']!=row['profile'] or info['samples']!=geometry['samples'] or geometry['start']!=offset:
                raise ValueError('Original reset geometry/profile changed')
            offset+=info['samples'];blobs.append(blob);infos.append(info)
        if offset!=row['samples'] or sum(map(len,blobs))!=row['expected_bytes']:raise ValueError('Complete source size/length mismatch')
        group=(row['family'],row['split'],row['cohort'],row['profile']);hist_groups[group].extend(blobs)
        for info in infos:
            coded=parameter_codes(info['params'])
            group_unused[group]['stored_gain_zero_tuples']+=sum(gain==0 for scale,lag,gain in coded)
            group_unused[group]['gain_zero_lag_changes']+=sum(b[2]==0 and b[1]!=a[1] for a,b in zip(coded,coded[1:]))
            group_unused[group]['scale_code_alias_values_0_to_5_retained']+=sum(scale<=5 for scale,lag,gain in coded)
        for method in METHODS:
            cost=chain_cost(blobs,method,infos);parts=cost['segment_costs']
            public={'id':row['id'],'case':row['case'],'family':row['family'],'domain':row['domain'],'profile':row['profile'],
                'split':row['split'],'cohort':row['cohort'],'samples':row['samples'],'method':asdict(method),
                'segments':len(blobs),'current_file_bytes':cost['current_file_bytes'],'proposed_file_bytes':cost['proposed_file_bytes'],
                'whole_stream_saved_bytes':cost['whole_stream_saved_bytes'],'added_decoder_flash_data_upper_bound_bytes':cost['whole_stream_saved_bytes'],
                'fallback_data_only_upper_bound_bytes':cost['fallback_data_only_upper_bound_bytes'],
                'all_segment_sizes_within_rom_api':all(c['same_rom_api_size_fits'] for c in parts),
                'field_absolute_escapes':{field:sum(c['parameter_detail']['fields'][field]['absolute_escapes'] for c in parts) for field in ('scale','lag','gain_code')},
                'segment_costs':[{k:v for k,v in c.items() if k not in ('method','parameter_detail')} for c in parts],
                'format_implemented':False,'decoder_flash_measured':False}
            cost_rows.append(public)
        private_records.append({'id':row['id'],'private_case_id':row['private_case_id'],'family':row['family'],
            'streams':[{'path':str(Path(s['path']).resolve()),'sha256':s['stream_sha256']} for s in row['segments']]})
        if ordinal==len(training):
            nomination=nominate(cost_rows);save(output/'nomination-lock-private.json',{'nomination':nomination,'source_binding_sha256':sha(canonical(binding)),
                'input_manifests_sha256':private_inputs,'heldout_or_nonspeech_costs_processed':0})
        if ordinal%20==0:print(json.dumps({'processed_source_profiles':ordinal,'requested':460,'tuning_nomination_locked':nomination is not None}),flush=True)
    if nomination!=nominate(cost_rows):raise AssertionError('Heldout data changed tuning nomination')
    for path,digest in {**private_inputs,**stream_files}.items():
        if sha(Path(path).read_bytes())!=digest:raise ValueError('Frozen input changed during cost study')
    if source_binding()!=binding:raise ValueError('Cost source/runtime changed during study')
    groups=[]
    for family,split,cohort,profile in sorted(hist_groups):
        for method in METHODS:
            chosen=[r for r in cost_rows if (r['family'],r['split'],r['cohort'],r['profile'])==(family,split,cohort,profile) and r['method']['name']==method.name]
            groups.append({'family':family,'split':split,'cohort':cohort,'profile':profile,'method':asdict(method),**cost_summary(chosen)})
    broad=[]
    for family in sorted({r['family'] for r in cost_rows}):
        for split in sorted({r['split'] for r in cost_rows if r['family']==family}):
            for method in METHODS:
                chosen=[r for r in cost_rows if r['family']==family and r['split']==split and r['method']['name']==method.name]
                broad.append({'family':family,'split':split,'method':asdict(method),**cost_summary(chosen)})
    histograms=[{'family':k[0],'split':k[1],'cohort':k[2],'profile':k[3],
        'unused_but_preserved':dict(group_unused[k]),'histogram':parameter_histograms(blobs)} for k,blobs in sorted(hist_groups.items())]
    summary={'schema':'lpx-v5-hypothetical-parameter-study-v1','status':'complete','source_profiles':460,'cost_rows':len(cost_rows),
        'main_baseline_profiles':98,'expanded100_selected_profiles':98,'non_speech_baseline_profiles':264,'non_speech_cases':132,
        'unique_v5_streams_inspected':len(inspections),'assumptions':ASSUMPTIONS,'methods':[asdict(m) for m in METHODS],
        'nomination':nomination,'groups':groups,'family_split_totals':broad,'elapsed_seconds':time.perf_counter()-started,'process_cpu_seconds':time.process_time()-cpu,
        'quality_metrics_computed':False,'new_format_or_decoder_implemented':False,'firmware_flash_saving_measured':False,
        'scope':'Exact hypothetical complete bytes under declared syntax/header/padding only. All actual nonparameter bits retained. Data savings are optimistic per-image allowances for new decoder/table/layout cost; aggregate corpus totals are not a single firmware budget.'}
    save(output/'summary.json',summary);save(output/'rows.json',{'schema':'lpx-v5-hypothetical-parameter-rows-v1','rows':cost_rows})
    save(output/'histograms.json',{'schema':'lpx-v5-parameter-study-histograms-v1','groups':histograms})
    save(output/'nomination.json',nomination);save(output/'source-runtime.json',{**binding,'measurement_driver_sha256':sha(Path(__file__).read_bytes()),'private_input_fingerprints_exported':False})
    save(output/'results-private.json',{'status':'complete','input_manifests_sha256':private_inputs,'stream_files_sha256':stream_files,'source_binding_sha256':sha(canonical(binding)),'records':private_records})
    print(json.dumps({'status':'complete','source_profiles':460,'cost_rows':len(cost_rows),'nominees':{k:None if nomination[k] is None else nomination[k]['method']['name'] for k in ('minimal_repeat','higher_complexity_rice')},'seconds':summary['elapsed_seconds']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('baseline',type=Path);parser.add_argument('nonspeech',type=Path)
    parser.add_argument('expanded',nargs=3,type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.baseline,args.expanded,args.nonspeech,args.output)
