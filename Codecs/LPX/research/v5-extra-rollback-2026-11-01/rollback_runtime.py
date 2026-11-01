"""Frozen source/native bridges and saved comparisons; no eager codec imports."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'v5-existing-extra-pass-2026-11-01'
V1=HERE.parent/'v5-joint-rate-2026-11-01'
sys.path.insert(0,str(PREVIOUS));sys.path.insert(0,str(V1))
from pilot_runtime import (Inputs,VALUE_KEYS,WholeEvaluator,bind_production,production_snapshot,
    load_production,check_origins,equal,save,sha,bridge_native,no_initial_fits,target_for,
    load_manifest as load_original_manifest)
from extra_policy import eligible_groups
from extra_runtime import MEASUREMENT_TOOLS,PREFIX
from secondary import read_prior,same_context

SOURCE_COMMIT='806d0c4931c95075d7ea1bffec1ce870d1d06631'
PRIOR_ARMS={'joint-rate-v1':('T-local-0','T-full-0','G-full-0','G-full-.1','G-full-1'),
    'anchor-order':('T-time-0','T-priority-0','G-time-0','G-priority-0'),
    'existing-extra-pass':('legacy','causal')}


def source_snapshot():
    paths=[p for p in HERE.iterdir() if p.suffix in ('.py','.md')]
    paths += [V1/name for name in ('baselines.py','pilot_policy.py','pilot_runtime.py')]
    paths += [PREVIOUS/name for name in ('extra_policy.py','extra_runtime.py','secondary.py')]
    shared=HERE.parent/'v5-matched-search-cpu-2026-10-30'
    paths += [shared/name for name in ('study_policy.py','study_runtime.py')]
    return {p.relative_to(HERE.parent).as_posix():sha(p.read_bytes()) for p in paths}


def measurement_bridge(old,inventory,runtime,native):
    names={name for name in inventory if name.startswith(PREFIX+'src/')}
    names.update(PREFIX+'tools/'+name for name in MEASUREMENT_TOOLS)
    before=old['production_sources']
    if ({name for name in before if name.startswith(PREFIX+'src/')}!=
            {name for name in inventory if name.startswith(PREFIX+'src/')} or
            any(before.get(name)!=inventory.get(name) or name not in inventory for name in names)):
        raise ValueError('Saved whole measurement DSP/metric closure changed')
    if old['runtime']!=runtime:raise ValueError('Saved numerical package/thread runtime changed')
    for key in ('library_sha256','unchanged_native_source_closure','callback_enabled','rom_pointer','assembly','build_receipts'):
        if old['native_bridge'][key]!=native[key]:raise ValueError('Saved native binary/recipe closure changed')
    return dict(status='PASS',old_source_commit=old['source_commit'],current_source_commit=SOURCE_COMMIT,
        unchanged_measurement_sources={name:inventory[name] for name in sorted(names)},
        recorded_runtime_exact=True,native_binary_and_recipe_exact=True,old_metrics_remain_saved_not_fresh=True,
        scope='Measurement dependency bridge only; extracted encoder state owner has a new epoch')


def function_span(path,name):
    raw=Path(path).read_bytes();text=raw.decode();tree=ast.parse(text)
    found=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name]
    if len(found)!=1:raise ValueError('Expected exactly one top-level optional-pulse operator')
    node=found[0];first=min([node.lineno]+[d.lineno for d in node.decorator_list])
    span='\n'.join(text.splitlines()[first-1:node.end_lineno])+'\n'
    return dict(source_sha256=sha(span.encode()),ast_sha256=sha(ast.dump(node,include_attributes=False).encode()))


def operator_bridge(current_root,old_binding,inputs):
    name=PREFIX+'tools/refine_speech_extras.py';old_path=Path(old_binding['source_root'])/name
    inputs.read(old_path,old_binding['production_sources'][name]);inputs.read(current_root/name)
    old=function_span(old_path,'refit_extra_group');new=function_span(current_root/name,'refit_extra_group')
    if old['ast_sha256']!=new['ast_sha256']:raise ValueError('The cheap causal group operator AST changed')
    dependencies=('enhance_speech_compact.py','q0_model.py','wav_lpc.py','speech_compact.py',
        'speech_v4.py','lpx4.py','rice_v7.py','rice_v3.py','rice_v4_reference.py','l3av_parse.py')
    closure={}
    for file in dependencies:
        relative=PREFIX+'tools/'+file;digest=old_binding['production_sources'][relative]
        inputs.read(Path(old_binding['source_root'])/relative,digest);inputs.read(current_root/relative,digest)
        closure[relative]=digest
    return dict(status='PASS',old_wrapper_state_epoch=old_binding['source_commit'],new_wrapper_state_epoch=SOURCE_COMMIT,
        function='refit_extra_group',old_function=old,new_function=new,exact_ast=True,
        exact_function_source=old['source_sha256']==new['source_sha256'],unchanged_arithmetic_packing_dependencies=closure,
        scope='Function/dependency bridge; fresh control slot-byte consistency is checked separately')


def prior_full_pass(export,bases,inputs):
    export=Path(export);raw=inputs.read(export/'binding-private.json');binding=json.loads(raw)
    marker=inputs.json(export/'complete-private.json');summary=inputs.json(export/'summary.json')
    if (binding['status']!='PASS' or marker['status']!='complete' or marker['binding_sha256']!=sha(raw) or
            summary['status']!='PASS' or summary['arm_records']!=12 or summary['corpus_helper_calls']!=20 or summary['actual_cap_views']!=36):
        raise ValueError('The saved full-pass export is not closed')
    def closed(path):
        path=Path(path).resolve();digest=binding['input_files_sha256'].get(str(path))
        if digest is None:raise ValueError('The saved full-pass export omitted an authoritative receipt')
        return inputs.json(path,digest)
    old_manifest=closed(binding['baselines_path']);old_bases={b['id']:b for b in old_manifest['baselines']}
    current={b['id']:b for b in bases};rows=[];producers=[];controls={}
    for arm in ('legacy','causal'):
        shard=Path(binding['arguments'][arm]);producer=closed(shard/'binding-private.json')
        attempt=closed(shard/'attempt-private.json');records=closed(shard/'results-private.json')
        if attempt['status']!='complete' or attempt['forbidden_fit_or_build_attempts']:
            raise ValueError('Saved full-pass worker failed')
        producers.append(producer)
        for record in records:
            if record['baseline_id'] not in current:continue
            base=current[record['baseline_id']];same_context(base,old_bases[base['id']])
            if len(record['whole_rows'])!=len(record['whole_chains']):raise ValueError('Saved whole catalogue differs')
            for value,chain in zip(record['whole_rows'],record['whole_chains']):
                if value['id']!=chain['id']:raise ValueError('Saved whole row/tuple ID differs')
                if not value['automatic_quality_eligible']:continue
                parts=tuple(inputs.stream(m) for m in chain['segments'])
                if sum(map(len,parts))!=value['stream_bytes']:raise ValueError('Saved whole byte cost differs')
                rows.append(dict(study='existing-extra-pass',arm=arm,baseline_id=base['id'],job_id=record['id'],candidate_id=value['id'],
                    stream_bytes=value['stream_bytes'],segments=chain['segments'],value={k:value[k] for k in VALUE_KEYS},
                    provenance='Old full-pass whole measurement, saved and unseeded'))
            if arm=='causal':
                local=sorted(record['locals'],key=lambda r:r['index'])
                if [r['index'] for r in local]!=list(range(len(base['segments']))):raise ValueError('Saved causal control reset coverage differs')
                slots=[]
                for slot in range(1,5):
                    metas=[]
                    for reset in local:
                        report=reset['report'];checkpoints=report['checkpoints']
                        matches=[r for r in checkpoints if r['slot']==slot]
                        if len(matches)!=1 or matches[0]['status']!='complete':raise ValueError('Saved actual causal checkpoint is missing')
                        points={point['id']:point for point in report['candidates']}
                        captured={meta['id']:meta for meta in reset['captured_streams']}
                        if len(points)!=len(report['candidates']) or len(captured)!=len(reset['captured_streams']):
                            raise ValueError('Saved actual candidate IDs are not unique')
                        point=points[matches[0]['candidate_id']]
                        if 'checkpoint-'+str(slot) not in point['labels']:raise ValueError('Saved slot publication label differs')
                        meta=captured[point['id']]
                        if meta['id']!=point['id']:raise ValueError('Saved captured candidate ID differs')
                        inputs.stream(meta);metas.append(meta)
                    slots.append(dict(slot=slot,segments=metas))
                controls[str(base['id'])]=dict(slots=slots,source_commit=producer['source_commit'],
                    source_binding_path=str((shard/'binding-private.json').resolve()),
                    provenance='Explicit old causal checkpoint slot -> candidate_id -> captured bytes')
    if len(controls)!=2:raise ValueError('Both exact old causal control contexts are required')
    return rows,producers,controls


def prior_rank(row):
    return (row['value']['score'],row['stream_bytes'],list(PRIOR_ARMS).index(row['study']),
        PRIOR_ARMS[row['study']].index(row['arm']),row['job_id'],row['candidate_id'])


def choose_prior(rows,cap,admission,anchor):
    available=[r for r in rows if r['stream_bytes']<=cap and all(admission(r['value'],anchor).values())]
    return None if not available else min(available,key=prior_rank)


def load_manifest(path,inputs):
    raw=inputs.read(path);manifest=json.loads(raw);marker=inputs.json(path.parent/'complete-private.json')
    if (manifest['schema']!='lpx-extra-rollback-study-private-v1' or manifest['status']!='prepared-no-search' or
            marker['status']!='complete' or marker['binding_sha256']!=sha(raw)):
        raise ValueError('Rollback original-input preparation is not closed')
    for name,digest in manifest['input_files_sha256'].items():inputs.read(name,digest)
    for name,digest in manifest['research_sources'].items():inputs.read(HERE.parent/name,digest)
    return manifest


def verify_preflight(path,manifest_path,inputs,expected):
    """Closed exact-current proof, including prepared path AND pinned digest."""
    path=Path(path).resolve();manifest_path=Path(manifest_path).resolve()
    marker=inputs.json(path/'complete-private.json')
    def closed(name):
        raw=inputs.read(path/name)
        if marker['output_sha256'].get(name)!=sha(raw):raise ValueError('Preflight terminal marker differs')
        return json.loads(raw)
    summary=closed('summary.json');proof=closed('binding-private.json');attempt=closed('attempt-private.json')
    synthetic=closed('synthetic-results-private.json');real=closed('results-private.json')
    if (marker['status']!='complete' or summary['status']!='PASS' or summary['mode']!='preflight' or
            summary['real_arm_records']!=0 or summary['real_pass_instances']!=0 or summary['real_stage_events']!=0 or
            summary['real_cap_views']!=0 or summary['synthetic_arm_records']!=6 or summary['synthetic_pass_instances']!=8 or
            summary['synthetic_stage_events']!=24 or summary['synthetic_cap_views']!=18 or
            any(summary[name]!=0 for name in ('initial_fits','native_builds','target_jobs')) or
            attempt['status']!='complete' or attempt['real_instances'] or len(attempt['synthetic_instances'])!=8 or
            any(row['status']!='complete' for row in attempt['synthetic_instances']) or
            attempt['forbidden_fit_or_build_attempts'] or len(synthetic)!=6 or real!=[] or
            len(attempt['records'])!=6 or any(r['phase']!='synthetic' or r['status']!='complete' for r in attempt['records'])):
        raise ValueError('Required six-record/eight-instance synthetic preflight is not closed')
    for name in ('source_commit','production_sources','research_sources','runtime','native_bridge','source_context'):
        if proof[name]!=expected[name]:raise ValueError('Preflight '+name+' differs from the current context')
    if Path(proof['source_root']).resolve()!=Path(expected['source_root']).resolve() or proof['mode']!='preflight' or proof['assigned_jobs']!=[]:
        raise ValueError('Preflight root or assigned real scope differs')
    if Path(proof['baselines_path']).resolve()!=manifest_path:raise ValueError('Preflight prepared manifest path differs')
    digest=sha(inputs.read(manifest_path))
    if proof['input_files_sha256'].get(str(manifest_path))!=digest:raise ValueError('Preflight prepared manifest digest differs')
    return dict(status='PASS',preflight_path=str(path),prepared_manifest_path=str(manifest_path),prepared_manifest_sha256=digest,
        exact_closed_research_production_native_runtime=True,synthetic_arm_records=6,synthetic_pass_instances=8)
