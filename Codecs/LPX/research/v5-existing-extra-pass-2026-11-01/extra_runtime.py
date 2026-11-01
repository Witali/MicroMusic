"""Explicit frozen origins and unchanged-measurement bridge for old evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
V1=HERE.parent/'v5-joint-rate-2026-11-01'
sys.path.insert(0,str(V1))
from baselines import Inputs,sha
from pilot_policy import distinct_whole
from pilot_runtime import (VALUE_KEYS,WholeEvaluator,bind_production,production_snapshot,load_production,
    check_origins,equal,save,no_initial_fits,bridge_native,target_for,load_manifest as load_original_manifest)

# Integration's exact clean execution epoch, held fixed through final export.
SOURCE_COMMIT='de78a32376f9f9c17b64720a1a108ac85a3cf74b'
HISTORICAL_RESEARCH_COMMIT='3f256c1d4d4e83b76fb570abe0d0ec8e2c5b4f4a'
PREFIX='Codecs/LPX/01_ACTIVE_Q0_CODEC/'
MEASUREMENT_TOOLS=('adaptive_speech_chain.py','speech_compact.py','speech_v4.py','lpx4.py',
    'q0_model.py','wav_lpc.py','rice_v7.py','enhance_speech_compact.py','refine_speech_compact.py',
    'standard_metrics.py','voice_character.py','speech_noise_objective.py','speech_voice_objective.py',
    'voice_input.py','tune_pcm16.py','batch_decoder.py','rice_v3.py','rice_v4_reference.py','l3av_parse.py')


def source_snapshot():
    paths=[p for p in HERE.iterdir() if p.suffix in ('.py','.md')]
    paths += [V1/name for name in ('baselines.py','pilot_policy.py','pilot_runtime.py','run_pilot.py')]
    shared=HERE.parent/'v5-matched-search-cpu-2026-10-30'
    paths += [shared/name for name in ('study_policy.py','study_runtime.py')]
    return {p.relative_to(HERE.parent).as_posix():sha(p.read_bytes()) for p in paths}


def measurement_bridge(old_binding,inventory,runtime,native_bridge):
    """Old measurements stay old; only declared unchanged dependencies compare."""
    old=old_binding['production_sources']
    names={name for name in inventory if name.startswith(PREFIX+'src/')}
    names.update(PREFIX+'tools/'+name for name in MEASUREMENT_TOOLS)
    if ({name for name in old if name.startswith(PREFIX+'src/')}!=
            {name for name in inventory if name.startswith(PREFIX+'src/')} or
            any(name not in old or name not in inventory or old[name]!=inventory[name] for name in names)):
        raise ValueError('Prior saved comparison has a changed DSP/metric dependency')
    if old_binding['runtime']!=runtime:
        raise ValueError('Prior recorded Python/package/thread runtime differs')
    prior_native=old_binding['native_bridge']
    for key in ('library_sha256','unchanged_native_source_closure','callback_enabled','rom_pointer','assembly'):
        if prior_native[key]!=native_bridge[key]:raise ValueError('Prior native binary/recipe closure differs')
    if prior_native['build_receipts']!=native_bridge['build_receipts']:
        raise ValueError('Prior compiler/flags/build evidence differs')
    return dict(status='PASS',prior_source_commit=old_binding['source_commit'],
        current_source_commit=SOURCE_COMMIT,unchanged_measurement_files={name:inventory[name] for name in sorted(names)},
        recorded_runtime_exact=True,native_binary_and_recipe_exact=True,
        old_measurements_remain_saved_not_fresh=True,
        scope='Exact recorded source/native/runtime bridge, not a new target/LTO or installed-package binary audit')


def load_manifest(path,inputs):
    raw=inputs.read(path);manifest=json.loads(raw);marker=inputs.json(path.parent/'complete-private.json')
    if (manifest['schema']!='lpx-existing-extra-study-private-v1' or manifest['status']!='prepared-no-search' or
            marker['status']!='complete' or marker['binding_sha256']!=sha(raw)):
        raise ValueError('The original-input no-search preparation is not closed')
    for name,digest in manifest['input_files_sha256'].items():inputs.read(name,digest)
    for name,digest in manifest['preparation_sources'].items():inputs.read(HERE.parent/name,digest)
    return manifest


def historical_preflight(path,inputs,inventory,runtime,native_bridge,original_digest):
    """Bind paid superseded work without treating changed old sources as current."""
    path=Path(path)
    summary=inputs.json(path/'summary.json');binding=inputs.json(path/'binding-private.json')
    attempt=inputs.json(path/'attempt-private.json');synthetic=inputs.json(path/'synthetic-private.json')
    if (summary['status']!='PASS' or not summary['preflight_only'] or summary['synthetic_helper_calls']!=6 or
            summary['corpus_helper_calls'] or summary['arm_records'] or summary['actual_cap_views'] or
            attempt['status']!='complete' or attempt['helper_calls'] or len(attempt['synthetic_calls'])!=6 or
            any(r['status']!='complete' for r in attempt['synthetic_calls']) or
            attempt['forbidden_fit_or_build_attempts'] or synthetic['status']!='PASS' or synthetic['helper_calls']!=6):
        raise ValueError('Historical six-call synthetic preparation is not complete')
    if (binding['source_commit']!=SOURCE_COMMIT or binding['production_sources']!=inventory or
            binding['runtime']!=runtime or binding['native_bridge']!=native_bridge):
        raise ValueError('Historical synthetic preparation used another production/native/runtime context')
    baseline_path=Path(binding['baselines_path']).resolve()
    digest=binding['input_files_sha256'].get(str(baseline_path))
    if digest is None:raise ValueError('Historical preflight did not bind its preparation')
    raw=inputs.read(baseline_path,digest);baseline=json.loads(raw)
    marker=inputs.json(baseline_path.parent/'complete-private.json')
    if (marker['status']!='complete' or marker['binding_sha256']!=sha(raw) or
            baseline['preparation_commit']!=HISTORICAL_RESEARCH_COMMIT or
            baseline['original_binding_sha256']!=original_digest):
        raise ValueError('Historical original-input preparation provenance differs')
    return dict(status='PASS',preflight_path=str(path.resolve()),preparation_path=str(baseline_path),
        historical_research_commit=baseline['preparation_commit'],historical_research_sources=binding['research_sources'],
        synthetic_helper_calls=6,corpus_helper_calls=0,preflight_cost=summary['total_cost'],
        superseded_metadata_preparation_cost=baseline['preparation_cost'],
        accounting='Shared historical paid preparation, counted once; old research sources are not current')
