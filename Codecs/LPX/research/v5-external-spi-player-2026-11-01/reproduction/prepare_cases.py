"""Prepare the fixed SPI/ROM cases and full host-native references, without fitting."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_inputs as native_module
from native_inputs import (Inputs,NativeInputs,REPRO,bind_source,load_tools,save_new,
    sha,source_inventory)

IMAGE_BYTES = 16*1024*1024
FIRST_OFFSET = 0x010203
LONG_SAMPLES = 3786111
VALUE_KEYS = ('metrics','voice','pwm_voice','noise','pwm_noise','domain_scores','score',
    'clipped_samples','voice_components','pwm_voice_components')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def normalized(path):
    return os.path.normcase(os.path.abspath(str(path)))


def descriptors(parts):
    return tuple((p['stream_sha256'],p['file_bytes'],p['index'],p['start'],p['samples'],p['profile']) for p in parts)


def gates(row,anchor):
    old = True
    for domain in ('pcm16','pwm8'):
        new,before = row['metrics'][domain],anchor['metrics'][domain]
        old &= new['error_energy']<=before['error_energy']
        if before['stoi'] is not None:
            old &= new['stoi'] is not None and new['stoi']>=before['stoi']-1e-12
    return dict(old_pcm_pwm_floors_passed=bool(old),
        clipped_sample_floor_passed=row['clipped_samples']<=anchor['clipped_samples'],
        pcm_period_coverage_floor_passed=row['voice']['within_tolerance_frames']>=anchor['voice']['within_tolerance_frames'],
        pwm_period_coverage_floor_passed=row['pwm_voice']['within_tolerance_frames']>=anchor['pwm_voice']['within_tolerance_frames'],
        joint_objective_nonregression=row['score']<=anchor['score']+1e-12)


def choose(rows,cap):
    fit = [r for r in rows if r['stream_bytes']<=cap]
    good = [r for r in fit if r['automatic_quality_eligible']]
    key = lambda r:(r['score'],r['stream_bytes'],r['id'])
    return dict(selected_id=None if not good else min(good,key=key)['id'],
        raw_id=None if not fit else min(fit,key=key)['id'],cap=cap,full_flash_cap=None,
        fitting_chains=len(fit),eligible_chains=len(good),no_fit=not fit,no_automatic_admission=not good)


def image_layout(sizes):
    offset = FIRST_OFFSET
    offsets = []
    if not sizes:
        raise ValueError('An external case needs at least one stored reset')
    for size in sizes:
        if type(size) is not int or not 22<=size<=65535 or offset+size>IMAGE_BYTES:
            raise ValueError('External image span or uint16 reset size is invalid')
        offsets.append(offset)
        offset += size
    return offsets


def write_image(path,blobs):
    offsets = image_layout([len(b) for b in blobs])
    image = bytearray(b'\xff')*IMAGE_BYTES
    for offset,blob in zip(offsets,blobs):
        image[offset:offset+len(blob)] = blob
    with Path(path).open('xb') as stream:
        stream.write(image)
    if Path(path).stat().st_size!=IMAGE_BYTES:
        raise AssertionError('External image is not exactly 16 MiB')
    return offsets,sha(image)


def planned_rows(chains):
    rows = []
    for chain in chains:
        storages = ('spi',) if chain['kind']=='long' else ('spi','rom')
        assemblies = (True,) if chain['kind']=='long' else (False,True)
        for storage in storages:
            for assembly in assemblies:
                for irq in (0,100):
                    rows.append(dict(id='row-%03d'%(len(rows)+1),chain_id=chain['id'],storage=storage,
                        assembly=assembly,extra_irq_cycles=irq))
    if len(rows)!=28:
        raise ValueError('The fixed 12 long/8 short SPI/8 short ROM scope changed')
    return rows


def load_producer(study,original_study,inputs):
    export = study/'export-v1'
    exported = json.loads(inputs.read(export/'binding-private.json'))
    closed = {normalized(name):digest for name,digest in exported['inputs_sha256'].items()}
    def checked(path):
        digest = closed.get(normalized(path))
        if digest is None:
            raise ValueError('An authoritative producer receipt is not in the closed export binding')
        return json.loads(inputs.read(path,digest))
    summary = json.loads(inputs.read(export/'summary.json'))
    changed = json.loads(inputs.read(export/'changed-selected-chains-private.json'))
    if (summary['status']!='PASS' or summary['arm_records']!=248 or summary['helper_calls']!=312
            or summary['cap_views']!=744 or not summary['no_old_whole_metric_reuse']):
        raise ValueError('The complete fixed CPU comparison is required')
    baselines = checked(study/'baselines-v1/binding-private.json')
    bases = {b['id']:b for b in baselines['baselines']}
    jobs = {j['id']:j for j in baselines['jobs']}
    if len(bases)!=104 or len(jobs)!=248 or set(jobs)!=set(range(248)):
        raise ValueError('The common baseline or arm job inventory changed')
    rows,events = {},{}
    for shard in (0,1):
        folder = study/('replay-v1-shard-%d'%shard)
        binding = checked(folder/'binding-private.json')
        receipt = checked(folder/'summary.json')
        attempt = checked(folder/'attempt-private.json')
        values = checked(folder/'results-private.json')
        if (receipt['status']!='PASS' or attempt['status']!='complete' or receipt['warmup_only']
                or attempt['forbidden_fit_or_build_attempts'] or receipt['new_initial_fits']
                or binding['source_commit']!=summary['source_commit']):
            raise ValueError('A final producer worker is not a complete no-fit guarded result')
        for event in attempt['helper_calls']:
            key = event['job_id'],event['reset']
            if event['status']!='complete' or key in events:
                raise ValueError('A helper was incomplete or repeated')
            events[key] = event
        for row in values:
            index = row['id']
            if index in rows or row['source_ordinal']%2!=shard:
                raise ValueError('Producer arm identities overlap or violate source parity')
            if any(row[k]!=v for k,v in jobs[index].items()):
                raise ValueError('A producer arm differs from its fixed job')
            if not row['whole_rows'] or len(row['whole_rows'])!=len(row['whole_chains']):
                raise ValueError('Whole metric rows and ordered chains differ')
            if descriptors(row['whole_chains'][0]['segments'])!=descriptors(bases[row['baseline_id']]['segments']):
                raise ValueError('An arm does not start from its exact common baseline')
            anchor = row['whole_rows'][0]
            if any(anchor[k]!=bases[row['baseline_id']]['canonical_whole_value'][k] for k in VALUE_KEYS):
                raise ValueError('An arm anchor metric differs from its exact common canonical baseline')
            for identifier,(value,chain) in enumerate(zip(row['whole_rows'],row['whole_chains'])):
                if (value['id']!=identifier or chain['id']!=identifier or not math.isfinite(value['score'])
                        or value['stream_bytes']!=sum(p['file_bytes'] for p in chain['segments'])):
                    raise ValueError('Stored whole cost, identity or score differs')
                flags = gates(value,anchor)
                if any(value[k]!=v for k,v in flags.items()) or value['automatic_quality_eligible']!=all(flags.values()):
                    raise ValueError('A stored whole admission contradicts its current anchor')
            if [d['percent'] for d in row['decisions']]!=[100,95,90]:
                raise ValueError('The three original data caps changed')
            for decision in row['decisions']:
                percent = decision['percent']
                expected = choose(row['whole_rows'],bases[row['baseline_id']]['stream_bytes']*percent//100)
                if percent not in (100,95,90) or any(decision[k]!=v for k,v in expected.items()) or not decision['incumbent_nonregression']:
                    raise ValueError('An authoritative cap decision cannot be reproduced')
            rows[index] = row
    expected_events = {(j['id'],index) for j in jobs.values() for index in j['edited_segments']}
    if set(rows)!=set(jobs) or set(events)!=expected_events or len(events)!=312:
        raise ValueError('The exact 248 arm/312 actual helper scope is incomplete')
    for (job_id,index),event in events.items():
        if event['cpu_seconds']!=jobs[job_id]['cpu_seconds_per_reset'] or event['arm']!=jobs[job_id]['arm']:
            raise ValueError('An actual helper used another arm or CPU allowance')
    original = checked(original_study/'binding-private.json')
    if original['identity']!=sha(canonical({k:v for k,v in original.items() if k!='identity'})):
        raise ValueError('The original V2 preparation binding changed')
    base_inputs = {normalized(path):digest for path,digest in baselines['inputs_sha256'].items()}
    return dict(bases=bases,rows=rows,changed=changed,original=original,original_study=original_study,
        closed=closed,base_inputs=base_inputs,summary=summary)


def reference_context(base,producer,inputs,tools):
    original = producer['original']
    matches = [j for j in original['jobs'] if j['phase']=='nonspeech-default' and j['source_ordinal']==7
        and original['nonspeech_records'][j['record_index']]['profile']==base['profile']]
    if len(matches)!=1:
        raise ValueError('The fixed original long NS context is missing')
    job = matches[0]
    record = original['nonspeech_records'][job['record_index']]
    if record['reference']!=base['reference'] or job['mode']!=base['mode'] or base['mode']!='preserve':
        raise ValueError('The declared common reference/level context changed')
    folder = producer['original_study']/'records/nonspeech-default/source-007'/('profile-%d'%base['profile'])
    marker_path = folder/'complete-private.json'
    marker_digest = producer['closed'].get(normalized(marker_path))
    if marker_digest is None:
        raise ValueError('A used original completion marker is not in the closed producer binding')
    marker = json.loads(inputs.read(marker_path,marker_digest))
    report = json.loads(inputs.read(folder/'record-private.json',marker['report_sha256']))
    identity = sha(canonical([original['identity'],job]))
    if (marker['identity']!=identity or report['identity']!=identity or report['level']!=base['level']
            or report['target_reference_pcm16_sha256']!=base['target_reference_pcm16_sha256']):
        raise ValueError('A used long target level differs from its bound original')
    canonical_path = Path(base['source_result_path'])
    digest = producer['base_inputs'].get(normalized(canonical_path))
    if digest is None:
        raise ValueError('A used canonical source receipt is not bound')
    prior = json.loads(inputs.read(canonical_path,digest))
    selected = next(d['selected_id'] for d in prior['decisions'] if d['percent']==100)
    if (prior['phase']!=base['source_phase'] or prior['profile']!=base['profile'] or prior['source_ordinal']!=7
            or prior['samples']!=LONG_SAMPLES or prior['mode']!=base['mode'] or selected!=base['canonical_whole_candidate_id']
            or descriptors(prior['chains'][selected]['segments'])!=descriptors(base['segments'])
            or any(prior['report']['candidates'][selected][k]!=base['canonical_whole_value'][k] for k in VALUE_KEYS)):
        raise ValueError('The used common canonical100 baseline provenance differs')
    descriptor = base['reference']
    raw = inputs.read(descriptor['path'],descriptor['file_sha256'])
    if len(raw)!=descriptor['file_bytes']:
        raise ValueError('The used reference file length differs')
    import soundfile as sf
    pcm,rate = sf.read(descriptor['path'],dtype='int16')
    if (rate!=8000 or pcm.ndim!=1 or len(pcm)!=LONG_SAMPLES
            or sha(pcm.astype('<i2').tobytes())!=descriptor['pcm16_sha256']
            or descriptor['pcm16_sha256']!=base['target_reference_pcm16_sha256'] or base['level']['gain']!=1):
        raise ValueError('The full original-level NS PCM target changed')
    return dict(baseline_id=base['id'],reference=descriptor,level=base['level'],
        target_reference_pcm16_sha256=base['target_reference_pcm16_sha256'],
        canonical_source_result_path=str(canonical_path),original_record_path=str(folder/'record-private.json'))


def select_long_cases(producer,inputs,tools):
    bases = [b for b in producer['bases'].values() if b['nonspeech'] and b['source_ordinal']==7]
    if len(bases)!=2 or {b['profile'] for b in bases}!={4,6}:
        raise ValueError('Exactly two long common baselines are required')
    changed = [c for c in producer['changed'] if c['samples']==LONG_SAMPLES and len(c['segments'])==60]
    if len(changed)!=4 or Counter(c['profile'] for c in changed)!={4:2,6:2}:
        raise ValueError('Exactly four long changed tuples, two per profile, are required')
    cases,keys = [],set()
    for base in sorted(bases,key=lambda b:b['profile']):
        ref = reference_context(base,producer,inputs,tools)
        candidates = [(base['segments'],[dict(role='common-canonical100-baseline',baseline_id=base['id'])])]
        for item in changed:
            if item['profile']!=base['profile']:
                continue
            if not item['contexts']:
                raise ValueError('A changed tuple lacks authoritative selected contexts')
            for context in item['contexts']:
                row = producer['rows'][context['job_id']]
                decision = next(d for d in row['decisions'] if d['percent']==context['percent'])
                selected = decision['selected_id']
                if (selected is None or row['phase']!='nonspeech-default' or row['source_ordinal']!=7
                        or row['baseline_id']!=base['id'] or context['mode']!=base['mode']
                        or context['arm']!=row['arm'] or context['tier_label']!=row['tier_label']
                        or descriptors(row['whole_chains'][selected]['segments'])!=descriptors(item['segments'])
                        or descriptors(context['rollback'])!=descriptors(base['segments'])):
                    raise ValueError('A used changed tuple/rollback context differs from its actual decision')
            candidates.append((item['segments'],item['contexts']))
        for parts,contexts in candidates:
            if len(parts)!=60 or sum(p['samples'] for p in parts)!=LONG_SAMPLES:
                raise ValueError('A long tuple was shortened or lost its final reset')
            position = 0
            for index,part in enumerate(parts):
                if (part['index']!=index or part['start']!=position or part['profile']!=base['profile']
                        or not 1<=part['samples']<=64000):
                    raise ValueError('A long ordered reset boundary changed')
                position += part['samples']
            blobs = tuple(inputs.stream(p) for p in parts)
            if blobs in keys:
                raise ValueError('The fixed six long tuples are not byte-distinct')
            keys.add(blobs)
            cases.append(dict(id='long-%03d'%(len(cases)+1),kind='long',profile=base['profile'],samples=LONG_SAMPLES,
                segments=parts,blobs=blobs,contexts=contexts,reference_context=ref))
    return cases


def build_case(case,output,native,inputs):
    folder = output/'chains'/case['id']
    folder.mkdir(parents=True)
    blobs = case['blobs']
    offsets,image_sha = write_image(folder/'external-flash.bin',blobs)
    pcm_hash,pwm_hash = hashlib.sha256(),hashlib.sha256()
    used,samples = [],0
    with (folder/'expected.pcm16le').open('xb') as pcm_file,(folder/'expected.pwm8').open('xb') as pwm_file:
        for blob,part in zip(blobs,case['segments']):
            value = native.reference(blob,case['profile'],part['samples'])
            pcm = value['pcm'].astype('<i2').tobytes()
            pwm = value['pwm'].tobytes()
            pcm_file.write(pcm);pwm_file.write(pwm)
            pcm_hash.update(pcm);pwm_hash.update(pwm)
            used.append(value['used'])
            samples += len(value['pcm'])
    if samples!=case['samples'] or sum(used)>sum(map(len,blobs)):
        raise AssertionError('Complete reference coverage or requested-byte totals differ')
    for name in ('external-flash.bin','expected.pcm16le','expected.pwm8'):
        inputs.read(folder/name)
    return dict(**{k:v for k,v in case.items() if k not in ('blobs','segments')},
        segments=[dict(**part,external_offset=offset) for part,offset in zip(case['segments'],offsets)],
        stream_bytes=sum(map(len,blobs)),offsets=offsets,sizes=list(map(len,blobs)),
        external_image_path=str((folder/'external-flash.bin').resolve()),external_image_sha256=image_sha,
        expected_pwm_path=str((folder/'expected.pwm8').resolve()),expected_pwm_sha256=pwm_hash.hexdigest(),
        expected_pcm16_path=str((folder/'expected.pcm16le').resolve()),expected_pcm16_sha256=pcm_hash.hexdigest(),
        expected_payload_bytes=sum(used),payload_bytes_by_segment=used)


def prepare(args):
    started = time.perf_counter(),time.process_time()
    inputs = Inputs()
    inputs.read(sys.executable)
    sources = bind_source(args.source_root,args.source_commit,inputs)
    if Path(__file__).resolve().parent!=(args.source_root/REPRO).resolve():
        raise ValueError('Execute the preparation script from the merged frozen source root')
    if Path(native_module.__file__).resolve()!=(args.source_root/REPRO/'native_inputs.py').resolve():
        raise ValueError('The native reference adapter belongs to another worktree')
    producer = load_producer(args.producer_study,args.original_study,inputs)
    tools = load_tools(args.source_root)
    with ExitStack() as stack:
        def forbidden(*args,**kwargs):
            raise AssertionError('Fitting/search/AVR image work is forbidden during native case preparation')
        for name,attributes in {'speech_v4':('encode','search'),'speech_compact':('encode',),
                'batch_decoder':('build_library',)}.items():
            module = sys.modules.get(name)
            if module is not None:
                for attribute in attributes:
                    if hasattr(module,attribute):
                        stack.enter_context(patch.object(module,attribute,forbidden))
        cases = select_long_cases(producer,inputs,tools)
        for profile in (4,6):
            blob = tools.compact.repack(tools.fixture(profile,160))[0]
            folder = args.output/'synthetic'
            folder.mkdir(exist_ok=True)
            path = folder/('profile-%d.l4hy'%profile)
            with path.open('xb') as stream:
                stream.write(blob)
            inputs.read(path)
            cases.append(dict(id='short-p%d'%profile,kind='short',profile=profile,samples=160,blobs=(blob,),
                segments=[dict(index=0,start=0,samples=160,profile=profile,path=str(path.resolve()),
                    file_bytes=len(blob),stream_sha256=sha(blob))],contexts=[dict(role='deterministic-160-sample-fixture')]))
        native = NativeInputs(args.source_root,args.output,inputs,tools,args.compiler)
        completed = []
        for case in cases:
            completed.append(build_case(case,args.output,native,inputs))
            print(json.dumps(dict(status='native-case-complete',id=case['id'],samples=case['samples'])),flush=True)
    rows = planned_rows(completed)
    inputs.verify()
    if source_inventory(args.source_root)!=sources:
        raise ValueError('Native reference source changed during preparation')
    handoff = dict(schema='lpx-external-spi-cases-private-v1',status='prepared',input_files_sha256=inputs.pins,
        reference_source_sha256=sources,source_root=str(args.source_root),source_commit=args.source_commit,
        chains=completed,rows=rows,compiler=native.compiler,module_origins=tools.origins,
        native_reference_counts=dict(native.counts),external_image_bytes=IMAGE_BYTES,first_external_offset=FIRST_OFFSET,
        runtime=dict(python=sys.version,packages={name:__import__('importlib.metadata',fromlist=['version']).version(name)
            for name in ('numpy','numba','scipy','soundfile')}),
        payload_byte_semantics='Actual callback-requested stored-stream bytes, including header; SPI opcode/address excluded',
        source_input_output_guards_passed=True,new_fits=0,new_search_calls=0,avr_builds=0,simulation_jobs=0,
        cost=dict(wall_seconds=time.perf_counter()-started[0],cpu_seconds=time.process_time()-started[1]))
    save_new(args.output/'cases-private.json',handoff)
    save_new(args.output/'complete-private.json',dict(status='complete',handoff_sha256=sha((args.output/'cases-private.json').read_bytes()),
        chains=8,long_chains=6,synthetic_chains=2,rows=28,source_input_output_guards_passed=True,
        native_reference_counts=dict(native.counts),new_fits=0,new_search_calls=0,avr_builds=0,simulation_jobs=0))
    return handoff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','producer-study','original-study','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--compiler',default='g++')
    args = parser.parse_args()
    for name in ('source_root','producer_study','original_study','output'):
        setattr(args,name,getattr(args,name).resolve())
    if args.output.exists() or not args.output.is_relative_to((args.source_root/'build').resolve()):
        parser.error('Use fresh immutable output under the merged source-root build directory')
    args.output.mkdir(parents=True)
    save_new(args.output/'started-private.json',dict(status='started',new_fits=0,new_search_calls=0,avr_builds=0,simulation_jobs=0))
    try:
        result = prepare(args)
        print(json.dumps(dict(status='prepared',chains=len(result['chains']),rows=len(result['rows']),
            native_reference_counts=result['native_reference_counts'])),flush=True)
        return 0
    except Exception as exc:
        save_new(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception_type=type(exc).__name__)),flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
