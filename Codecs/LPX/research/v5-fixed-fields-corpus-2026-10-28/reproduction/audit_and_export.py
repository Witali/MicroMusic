"""Independently audit the complete fixed-fields corpus run and export anonymous data."""
from __future__ import annotations
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time

ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
import numpy as np
import soundfile as sf
import speech_compact as compact
from batch_decoder import BatchSession
from refine_speech_compact import quality,no_regression
from standard_metrics import pwm_duties
from measure_speech_firmware import checked_output
from output_paths import protect_outputs

sha=lambda data:hashlib.sha256(data).hexdigest()
canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
    checked_output(path)
    if path.is_symlink() or path.exists() and path.stat().st_nlink>1:raise ValueError('Audit output cannot alias another file')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def audit(manifest_path,study,output,driver_path):
    study=checked_output(study);output=checked_output(output);started=time.perf_counter();audit_source_sha=sha(Path(__file__).read_bytes())
    manifest_raw=Path(manifest_path).read_bytes();manifest=json.loads(manifest_raw);rows=manifest['records']
    progress=load(study/'progress-private.json');provenance=load(study/'provenance-private.json')
    if progress['status']!='complete' or progress['complete']!=list(range(98)) or len(rows)!=98:
        raise ValueError('Expected complete49case/98profile run')
    if provenance['manifest_sha256']!=sha(manifest_raw):raise ValueError('Manifest binding changed')
    if provenance['binding']['decoder_sources']!=manifest['source_sha256']:raise ValueError('Decoder differs from frozen incumbent source')
    module=runpy.run_path(str(driver_path),run_name='fixed_fields_driver_audit')
    if module['source_binding']()!=provenance['binding']:raise ValueError('Host/decoder/runtime source changed')
    libraries=provenance['native_libraries']
    for item in libraries.values():
        if sha(Path(item['path']).read_bytes())!=item['sha256']:raise ValueError('Native library binding changed')
    protect_outputs([Path(manifest_path),Path(driver_path),Path(__file__),study/'provenance-private.json',study/'progress-private.json',
        *[study/f'fixed-{i+1:03d}'/'results-private.json' for i in range(98)]],
        [output/name for name in ('summary.json','rows.json','generation.json','source-runtime.json','audit-private.json')])
    cases={};public_rows=[];public_generation=[];public_grids=[];private_checks=[];checked_blobs=set();artifacts=0;full_chain_points=0;accepted_trace_checks=0
    role_names=('amplitude','amplitude_original_selected','swapped_accepted','swapped_raw','observed_original_selected')
    with BatchSession('batch',prebuilt=Path(libraries['common']['path'])) as common, BatchSession('batch',prebuilt=Path(libraries['v5']['path'])) as v5:
        @lru_cache(maxsize=64)
        def validate(blob):
            samples=compact.unpack(blob)[0];model=compact.decode_model(blob)
            for decoder in (common,v5):
                pcm=decoder.decode_one_s16(blob,samples);pwm=decoder.decode_one(blob,samples)
                if pcm is None or pwm is None or not np.array_equal(pcm,model) or not np.array_equal(pwm,pwm_duties(model)):
                    raise AssertionError('Independent full-corpus native common/v5/model PCM/PWM mismatch')
            checked_blobs.add(sha(blob));return model
        for index,source in enumerate(rows):
            record=load(study/f'fixed-{index+1:03d}'/'results-private.json')
            unsigned={k:v for k,v in record.items() if k!='receipt_sha256'}
            if record['status']!='complete' or record['receipt_sha256']!=sha(canonical(unsigned)):
                raise ValueError('Incomplete or modified private record receipt')
            expected_identity=sha(canonical({'manifest':sha(manifest_raw),'record_index':index,'binding':provenance['binding'],
                'native_libraries':libraries}))
            if record['identity']!=expected_identity or record['record_index']!=index:
                raise ValueError('Private receipt belongs to a different frozen run')
            if any(record[key]!=source[key] for key in ('private_case_id','profile','split','cohort','samples')):
                raise ValueError('Record metadata differs from immutable manifest')
            if source['private_case_id'] not in cases:cases[source['private_case_id']]=f'case-{len(cases)+1:03d}'
            case=cases[source['private_case_id']];record_id=f'fixed-{index+1:03d}'
            reference_path=Path(source['reference']['path']);reference_bytes=reference_path.read_bytes()
            if sha(reference_bytes)!=source['reference']['file_sha256']:raise ValueError('Reference file changed since search')
            reference,rate=sf.read(reference_path,dtype='int16')
            if rate!=8000 or len(reference)!=source['samples'] or sha(reference.astype('<i2').tobytes())!=source['reference']['pcm16_sha256']:
                raise ValueError('Original full reference changed')
            seeds=[];seed_pcm=[];offset=0
            for ordinal,segment in enumerate(source['segments']):
                blob=Path(segment['path']).read_bytes()
                if sha(blob)!=segment['stream_sha256'] or len(blob)!=segment['file_bytes'] or segment['start']!=offset or segment['index']!=ordinal:
                    raise ValueError('Original ordered segment changed')
                seeds.append(blob);pcm=validate(blob);seed_pcm.append(pcm);offset+=len(pcm)
            baseline_pcm=np.concatenate(seed_pcm);baseline=quality(reference,baseline_pcm)
            if (offset!=len(reference) or sha(baseline_pcm.astype('<i2').tobytes())!=source['baseline_pcm16_sha256']
                    or sha(pwm_duties(baseline_pcm).tobytes())!=source['baseline_pwm_sha256']):
                raise ValueError('Original chain PCM/PWM binding changed')
            for artifact in record['artifacts']:
                path=Path(artifact['path'])
                if not path.resolve().is_relative_to((study/record_id).resolve()) or path.is_symlink() or path.stat().st_nlink!=1:
                    raise ValueError('Artifact escapes its original record')
                blob=path.read_bytes()
                if sha(blob)!=artifact['sha256']:raise ValueError('Recorded artifact changed')
                validate(blob);artifacts+=1
            public_grids.append({'id':record_id,'case':case,'profile':source['profile'],'grid':record['grid']})
            proposal_cache={};original_sse=int(baseline['pcm16']['error_energy']);ref64=reference.astype(np.int64)
            for proposal in record['generation']:
                a=Path(proposal['amplitude_path']).read_bytes();b=Path(proposal['swapped_path']).read_bytes();segment=proposal['segment']
                if compact.unpack(a)[:7]!=compact.unpack(seeds[segment])[:7] or compact.unpack(b)[:7]!=compact.unpack(seeds[segment])[:7]:
                    raise AssertionError('Fixed optional fields changed')
                if len(a)!=len(b) or len(a)!=proposal['amplitude_bytes'] or proposal['proposal_fit']!=(len(a)<=proposal['proposal_cap']):
                    raise AssertionError('Proposal lost equal complete-byte rate or feasibility')
                if proposal['render_evaluations']>128:raise AssertionError('Frozen render bound changed')
                amp=quality(reference,np.concatenate([*seed_pcm[:segment],validate(a),*seed_pcm[segment+1:]]))
                swap=quality(reference,np.concatenate([*seed_pcm[:segment],validate(b),*seed_pcm[segment+1:]]))
                if amp!=proposal['amplitude_metrics_in_original_context'] or swap!=proposal['swapped_metrics_in_original_context'] or not no_regression(swap,amp):
                    raise AssertionError('Complete original-context proposal metrics/gates changed')
                key=(segment,sha(a),proposal['proposal_fit'])
                if proposal['reused_identical_amplitude_seed']!=(key in proposal_cache):raise AssertionError('Incorrect equivalent search cache accounting')
                if key in proposal_cache:
                    if proposal['render_evaluations']!=0 or proposal['trace']!=proposal_cache[key]:raise AssertionError('Cached search changed accepted trace or render count')
                else:
                    if not 1+2*proposal['accepted_swaps']<=proposal['render_evaluations']<=128:raise AssertionError('Candidate/confirmation render bound violated')
                    values=compact.unpack(seeds[segment]);current=np.asarray(compact.unpack(a)[7],np.int64)
                    original_extras=np.asarray(values[7],np.int64);previous=int(amp['pcm16']['error_energy'])
                    start=source['segments'][segment]['start'];target=ref64[start:start+len(seed_pcm[segment])]
                    other=original_sse-int(np.sum((seed_pcm[segment].astype(np.int64)-target)**2))
                    for step in proposal['trace']:
                        incoming=step['restored_chunk'];outgoing=step['removed_chunk']
                        if current[incoming,1] or not current[outgoing,1] or not original_extras[incoming,1]:raise AssertionError('Accepted trace is not a retained/original-extra swap')
                        current[outgoing]=(-1,0);current[incoming]=original_extras[incoming]
                        intermediate=compact.pack(*values[:7],extras=current)[0]
                        pcm=validate(intermediate);score=other+int(np.sum((pcm.astype(np.int64)-target)**2))
                        if step['before_score']!=previous or step['after_score']!=score or score>=previous or len(intermediate)!=len(a):
                            raise AssertionError('Accepted snapshot trace differs from independent full integer rendering')
                        if not no_regression(quality(reference,np.concatenate([*seed_pcm[:segment],pcm,*seed_pcm[segment+1:]])),amp):
                            raise AssertionError('Accepted intermediate swap weakened frozen whole-context floors')
                        previous=score;accepted_trace_checks+=1
                    if proposal['trace'] and not np.array_equal(validate(compact.pack(*values[:7],extras=current)[0]),validate(b)):
                        raise AssertionError('Accepted swap trace does not produce stored final stream')
                    if len(proposal['trace'])!=proposal['accepted_swaps']:raise AssertionError('Accepted swap trace count changed')
                    proposal_cache[key]=proposal['trace']
                public_generation.append({'id':record_id,'case':case,'profile':source['profile'],'split':source['split'],'cohort':source['cohort'],
                    **{k:v for k,v in proposal.items() if k not in ('amplitude_path','swapped_path')}})
            if len(record['chains'])!=3 or {r['percent'] for r in record['chains']}!={100,95,90}:raise ValueError('Missing original cap row')
            for chain in record['chains']:
                cap=chain['max_complete_stream_bytes'];percent=chain['percent']
                if cap!=source['baseline_bytes']*percent//100 or chain['original_incumbent_metrics']!=baseline:
                    raise ValueError('Original total cap/metric binding changed')
                minimum=sum(item['minimum_fixed_bytes'] for item in record['grid'])
                if (chain['amplitude'] is not None)!=(minimum<=cap):
                    raise AssertionError('Finite pool lost exact all-extras-removed continuation')
                public={'id':record_id,'case':case,'profile':source['profile'],'split':source['split'],'cohort':source['cohort'],
                    'samples':source['samples'],'segments':len(seeds),'percent':percent,'max_complete_stream_bytes':cap,
                    'original_incumbent_bytes':source['baseline_bytes'],'original_incumbent_metrics':baseline,
                    'fixed_fields_minimum_bytes':minimum,'amplitude_selection':chain['amplitude_selection'],
                    'swapped_selection':chain['swapped_selection'],'whole_original_chain_rescored':True,
                    'original_selection_scope':chain['original_selection_scope'],'no_fit_scope':chain['no_fit_scope'],
                    'seconds':chain['seconds']}
                for role in role_names:
                    candidate=chain[role]
                    if candidate is None:public[role]=None;continue
                    streams=[Path(path).read_bytes() for path in candidate['paths']]
                    if len(streams)!=len(seeds) or sum(map(len,streams))!=candidate['file_bytes'] or candidate['file_bytes']>cap:
                        raise AssertionError('Complete role cap/geometry mismatch')
                    pcm=np.concatenate([validate(blob) for blob in streams]);metrics=quality(reference,pcm)
                    if metrics!=candidate['metrics'] or no_regression(metrics,baseline)!=candidate['original_incumbent_four_floors_passed']:
                        raise AssertionError('Independent full original-chain role metrics/gates changed')
                    public[role]={k:v for k,v in candidate.items() if k!='paths'};full_chain_points+=1
                amplitude=public['amplitude'];accepted=public['swapped_accepted'];raw=public['swapped_raw']
                if (amplitude is None)!=(accepted is None):raise AssertionError('Accepted swaps lost feasible amplitude rollback')
                if accepted is not None:
                    if not no_regression(accepted['metrics'],amplitude['metrics']):raise AssertionError('Final chain amplitude-control four floors regressed')
                    public['accepted_same_cap_amplitude_floors_passed']=True
                    old=amplitude['metrics']['pcm16']['error_energy'];new=accepted['metrics']['pcm16']['error_energy']
                    public['accepted_pcm_sse_change_percent_vs_amplitude']=100*(new-old)/old if old else 0
                    public['accepted_size_change_vs_amplitude']=accepted['file_bytes']-amplitude['file_bytes']
                else:
                    public['accepted_same_cap_amplitude_floors_passed']=None
                    public['accepted_pcm_sse_change_percent_vs_amplitude']=None
                    public['accepted_size_change_vs_amplitude']=None
                if raw is not None:
                    public['raw_same_cap_amplitude_floors_passed']=no_regression(raw['metrics'],amplitude['metrics'])
                public_rows.append(public)
            private_checks.append({'id':record_id,'identity':record['identity'],'receipt_sha256':record['receipt_sha256'],
                'artifacts':len(record['artifacts']),'elapsed_seconds':record['elapsed_seconds'],'python_process_cpu_seconds':record['python_process_cpu_seconds']})
            print(json.dumps({'audited':index+1,'requested':98,'id':record_id}),flush=True)
    if (Path(manifest_path).read_bytes()!=manifest_raw or module['source_binding']()!=provenance['binding']
            or sha(Path(__file__).read_bytes())!=audit_source_sha):
        raise ValueError('Frozen inputs/source changed during independent audit')
    for item in libraries.values():
        if sha(Path(item['path']).read_bytes())!=item['sha256']:raise ValueError('Native library changed during independent audit')
    groups=[]
    if (len(cases)!=49 or len(public_rows)!=294
            or any({r['profile'] for r in public_rows if r['case']==case}!={4,6} for case in cases.values())
            or any(count!=1 for count in Counter((r['case'],r['profile'],r['percent']) for r in public_rows).values())):
        raise ValueError('Expected both profiles for all49cases')
    def group_summary(chosen,labels):
        fit=[r for r in chosen if r['amplitude'] is not None];accepted=[r for r in chosen if r['swapped_accepted'] is not None]
        def outcomes():
            values=[r['accepted_pcm_sse_change_percent_vs_amplitude'] for r in fit]
            return [sum(value<0 for value in values),sum(value==0 for value in values),sum(value>0 for value in values)]
        before=sum(int(r['amplitude']['metrics']['pcm16']['error_energy']) for r in fit)
        after=sum(int(r['swapped_accepted']['metrics']['pcm16']['error_energy']) for r in fit)
        return {**labels,'records':len(chosen),'cases':len({r['case'] for r in chosen}),
            'amplitude_fits':len(fit),'swapped_accepted_fits':len(accepted),'no_fit':len(chosen)-len(fit),
            'accepted_pcm_sse_better_equal_worse_vs_amplitude':outcomes(),
            'common_fit_aggregate_pcm_sse_change_percent_vs_amplitude':100*(after-before)/before if before else 0,
            'accepted_original_four_floor_passes':sum(r['swapped_accepted'] is not None and r['swapped_accepted']['original_incumbent_four_floors_passed'] for r in chosen),
            'raw_original_four_floor_passes':sum(r['swapped_raw'] is not None and r['swapped_raw']['original_incumbent_four_floors_passed'] for r in chosen),
            'observed_original_selected':sum(r['observed_original_selected'] is not None for r in chosen),
            'all_accepted_amplitude_four_floors_preserved':all(r['accepted_same_cap_amplitude_floors_passed'] for r in fit),
            'amplitude_chain_evaluation_limits':sum(r['amplitude_selection']['evaluation_limit_reached'] for r in chosen),
            'swapped_chain_evaluation_limits':sum(r['swapped_selection'] is not None and r['swapped_selection']['evaluation_limit_reached'] for r in chosen)}
    for percent in (100,95,90):groups.append(group_summary([r for r in public_rows if r['percent']==percent],{'percent':percent,'split':'all','cohort':'all'}))
    for split,cohort in sorted({(r['split'],r['cohort']) for r in public_rows}):
        for percent in (100,95,90):groups.append(group_summary([r for r in public_rows if r['percent']==percent and r['split']==split and r['cohort']==cohort],{'percent':percent,'split':split,'cohort':cohort}))
    summary={'schema':'lpx-v5-fixed-fields-corpus-summary-v1','status':'complete','cases':49,'profile_groups':98,'original_cap_rows':len(public_rows),
        'segments':sum(r['segments'] for r in [load(study/f'fixed-{i+1:03d}'/'results-private.json') for i in range(98)]),
        'generation_rows':len(public_generation),'settings':provenance['binding']['settings'],'groups':groups,
        'generation_status_counts':dict(Counter(r['status'] for r in public_generation)),
        'render_evaluations':sum(r['render_evaluations'] for r in public_generation),
        'accepted_proposal_swaps':sum(r['accepted_swaps'] for r in public_generation if not r['reused_identical_amplitude_seed']),
        'search_record_wall_seconds_sum':sum(r['elapsed_seconds'] for r in private_checks),
        'search_python_process_cpu_seconds_sum':sum(r['python_process_cpu_seconds'] for r in private_checks),
        'parallel_campaign_wall_seconds':progress['elapsed_seconds'],'independent_audit_wall_seconds':time.perf_counter()-started,
        'independent_validated_unique_streams':len(checked_blobs),'independent_full_chain_points':full_chain_points,'artifact_rechecks':artifacts,
        'independent_accepted_intermediate_trace_checks':accepted_trace_checks,
        'all_current_common_v5_model_pcm_pwm_exact':True,'all_true_complete_caps_verified':True,
        'all_original_reference_files_levels_lengths_and_resets_verified':True,'retuned_on_evaluation_or_additional':False,
        'automatic_adoption':False,'mcu_source_changed':False,'physical_board_measured':False,
        'host_code_avr_program_flash_benefit_bytes':0,
        'scope':'Fixed original spectra/params/base pulses/filters only; original extra membership swaps and amplitude removal. Whole reset-chain byte/metric admission, finite cap grids and bounded chain selection. Original-incumbent versus same-cap amplitude comparisons are separate. Program/player Flash/IRQ and joint/nonzero-lambda comparisons belong to separate admission.'}
    public_provenance={**provenance['binding'],'native_libraries':{name:{'sha256':item['sha256']} for name,item in libraries.items()},
        'measurement_driver_sha256':sha(Path(driver_path).read_bytes()),'audit_export_driver_sha256':audit_source_sha,
        'private_manifest_and_per_media_bindings_exported':False}
    save(output/'summary.json',summary);save(output/'rows.json',{'schema':'lpx-v5-fixed-fields-corpus-rows-v1','rows':public_rows})
    save(output/'generation.json',{'schema':'lpx-v5-fixed-fields-corpus-generation-v1','grids':public_grids,'rows':public_generation})
    save(output/'source-runtime.json',public_provenance)
    save(output/'audit-private.json',{'manifest_sha256':sha(manifest_raw),'source_binding_sha256':sha(canonical(provenance['binding'])),'records':private_checks})
    print(json.dumps({'status':'complete','profile_groups':98,'rows':len(public_rows),'groups':groups[:3]}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','study','output','driver'):parser.add_argument(name,type=Path)
    args=parser.parse_args();audit(args.manifest,args.study,args.output,args.driver)
if __name__=='__main__':main()
