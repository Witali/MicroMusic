"""Fixed bounded player pilot; media and detailed linked evidence stay in build/."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path[:0] = [str(HERE), str(ACTIVE / 'tools'), str(ACTIVE / 'tests')]
import numpy as np
import speech_compact
from batch_decoder import BatchSession
from benchmark_speech_flash import canonical, source_hashes, validation_sources, validation_provenance
from build_release_observer import build as build_observer
from build_release_player import simulate, EXAMPLE, VALIDATION
from materialize import materialize
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
from scale_repeat import from_v5, to_v5
from speech_parameter_costs import METHODS, stream_cost
from standard_metrics import pwm_duties
from test_scale_repeat import build_native, unusual_source
from test_speech_v4 import fixture
import reference

sha = lambda data: hashlib.sha256(data).hexdigest()
load = lambda path: json.loads(Path(path).read_text())


def save(path, value):
    checked_output(path)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Pilot output alias')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def sources():
    files = [*HERE.glob('*.py'), *HERE.glob('*.patch'), HERE / 'lifecycle.cpp',
             ACTIVE / 'tests/test_speech_v4.py', ACTIVE / 'tests/test_speech_parameter_costs.py',
             *EXAMPLE.glob('*'), VALIDATION / 'sim_player.c', VALIDATION / 'player_hardware.cpp']
    return validation_sources(files)


def prepare(manifest_path):
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    records = manifest['records']
    if len(records) != 98 or manifest['source_sha256'] != source_hashes(ACTIVE / 'src'):
        raise ValueError('Expected frozen 49-record/both-profile manifest')
    result = []
    # Fixed before any target measurements. No selection by observed saving.
    for index in (0, 1, 40, 41, 85):
        row = records[index]
        if row['profile'] != (4 if index in (0, 40) else 6):
            raise ValueError('Fixed pilot profile changed')
        if index < 80 and row['split'] != 'tuning' or index == 85 and (row['samples'] != 281632 or len(row['segments']) != 5):
            raise ValueError('Fixed pilot geometry changed')
        parts = []
        offset = 0
        for number, part in enumerate(row['segments']):
            blob = Path(part['path']).read_bytes()
            if sha(blob) != part['stream_sha256'] or len(blob) != part['file_bytes'] or part['start'] != offset or part['index'] != number:
                raise ValueError('Frozen segment identity/geometry changed')
            if speech_compact.unpack(blob)[0] != part['samples'] or blob[5] & 127 != row['profile']:
                raise ValueError('Frozen segment protocol changed')
            offset += part['samples']
            parts.append(blob)
        if offset != row['samples'] or sum(map(len, parts)) != row['baseline_bytes']:
            raise ValueError('Frozen chain total changed')
        result.append({'id': 'manifest-index-%02d' % index,
                       'group': 'tuning-control' if row['split'] == 'tuning' else 'long-chain-correctness',
                       'profile': row['profile'], 'samples': row['samples'], 'streams': parts,
                       'baseline_pcm16_sha256': row['baseline_pcm16_sha256'],
                       'baseline_pwm_sha256': row['baseline_pwm_sha256']})
    for profile, count in ((4, 1), (6, 180), (6, 320)):
        if count == 320:
            values = speech_compact.unpack(speech_compact.repack(fixture(profile, count))[0])
            # Nonzero repeated scale exercises cached Q4 step after first tuple.
            params = [(24, 18, 0), (24, 145, 14)]
            blob = speech_compact.pack(values[0], profile, values[2], params, *values[4:7],
                                       extras=values[7], force_extras=True)[0]
        else:
            blob = unusual_source(profile, count)
        result.append({'id': 'synthetic-p%d-n%d' % (profile, count), 'group': 'synthetic-boundary',
                       'profile': profile, 'samples': count, 'streams': [blob]})
    return result, sha(raw)


def main(args):
    start = time.perf_counter()
    output = args.output.resolve()
    checked_output(output)
    baseline = source_hashes(ACTIVE / 'src')
    derived, patch_receipt = materialize(output / 'derived')
    frozen = sources()
    cases, manifest_digest = prepare(args.manifest)
    inputs = [args.manifest, *HERE.glob('*'), *(ACTIVE / 'src').glob('*')]
    protect_outputs(inputs, [output / name for name in ('results-private.json', 'summary.json', 'rows.json', 'source-runtime.json')])
    runner = build_observer(output / 'observer', args.include, args.lib, wsl=args.wsl)
    binding = {'schema': 'lpx-scale-repeat-pilot-provenance-v1', 'source': patch_receipt,
               'host_sources': frozen, 'validation': validation_provenance(runner, args.lib, args.wsl, sources=tuple(p for p in HERE.glob('*') if p.is_file())),
               'native_compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
               'prototype_code_commit': '64ffe977', 'format': 'L4HY version 6 / selector 1',
               'pilot_selection': 'Fixed manifest indices 0/1 and 40/41 (tuning); 85 (one long chain, correctness only); three synthetic boundaries. No retuning.',
               'production_source_unchanged': True, 'new_default': False, 'new_persistent_members': 0,
               'quality': 'Exact reconstruction required; no audibility claim.'}
    save(output / 'source-runtime.json', binding)
    native = [build_native(derived, output / ('native-' + str(only) + '.dll'), only) for only in (0, 1)]
    old_sessions = [BatchSession('batch', speech=True, speech_compact=True, compact_only=bool(only)) for only in (0, 1)]
    old = [session.__enter__() for session in old_sessions]
    private_rows = []
    public_rows = []
    try:
        for case in cases:
            if sources() != frozen or source_hashes(ACTIVE / 'src') != baseline or source_hashes(derived) != patch_receipt['derived_source_sha256']:
                raise ValueError('Frozen source changed during pilot')
            original = case['streams']
            experimental = [from_v5(blob) for blob in original]
            pcm_parts = []
            pwm_parts = []
            for before, after in zip(original, experimental):
                if to_v5(after) != before or reference.restore_v5(after)[0] != before:
                    raise AssertionError('Independent complete byte roundtrip failed')
                n = speech_compact.unpack(before)[0]
                pcm = speech_compact.decode_model(before)
                np.testing.assert_array_equal(reference.decode_model(after), pcm)
                if len(after) != stream_cost(before, METHODS[0])['proposed_file_bytes']:
                    raise AssertionError('Complete charged size differs from prior nomination')
                pwm = pwm_duties(pcm)
                for control, candidate in zip(old, native):
                    np.testing.assert_array_equal(control.decode_one_s16(before, n), pcm)
                    np.testing.assert_array_equal(control.decode_one(before, n), pwm)
                    np.testing.assert_array_equal(candidate.decode_one_s16(after, n), pcm)
                    np.testing.assert_array_equal(candidate.decode_one(after, n), pwm)
                pcm_parts.append(pcm)
                pwm_parts.append(pwm)
            expected = np.concatenate(pwm_parts).tobytes()
            if len(expected) != case['samples']:
                raise AssertionError('Complete original reset chain length mismatch')
            if 'baseline_pcm16_sha256' in case:
                if sha(np.concatenate(pcm_parts).astype('<i2').tobytes()) != case['baseline_pcm16_sha256'] or sha(expected) != case['baseline_pwm_sha256']:
                    raise AssertionError('Frozen original PCM/PWM changed')
            backends = (True, False) if case['id'] == 'manifest-index-01' else (True,)
            for assembly in backends:
                for irq in ((0, 100) if assembly else (0,)):
                    for role, streams, source in (('v5-control', original, ACTIVE / 'src'), ('v6-repeat', experimental, derived)):
                        folder = output / 'images' / case['id'] / ('asm' if assembly else 'c') / ('irq-' + str(irq)) / role
                        result = simulate(streams, folder, args.avr_bin, runner, source=source, queue=256,
                                          prefill=192, irq=irq, assembly=assembly, lib=args.lib, wsl=args.wsl,
                                          expected_pwm=expected, require_valid=False)
                        actual = (folder / 'valid.pcm8').read_bytes()
                        cost = result['cost']
                        row = {'id': case['id'], 'group': case['group'], 'profile': case['profile'],
                               'samples': case['samples'], 'segments': len(streams), 'role': role,
                               'backend': 'explicit-avr-asm' if assembly else 'explicit-c', 'extra_irq_cycles': irq,
                               'stream_bytes': sum(map(len, streams)), 'full_pwm_exact': actual == expected,
                               'complete_byte_roundtrip': True, 'independent_model_and_native_pcm_pwm_exact': True,
                               'flash_bytes': cost['flash_bytes'], 'program_flash_bytes': cost['program_flash_bytes'],
                               'static_sram_bytes': cost['static_sram_bytes'], 'data_bytes': cost['data_bytes'], 'bss_bytes': cost['bss_bytes'],
                               'flash_within32768': cost['flash_bytes'] <= 32768,
                               'timing_admitted': result['passed'], 'report': result['report']}
                        public_rows.append(row)
                        private_rows.append({**row, 'streams_sha256': [sha(blob) for blob in streams],
                                             'output': str(folder), 'verification': result,
                                             'adapter_sources_sha256': {name: value for name, value in frozen.items() if name.endswith(('scale_repeat.py', 'reference.py'))}})
                        save(output / 'rows.json', {'schema': 'lpx-scale-repeat-player-pilot-rows-v1', 'status': 'running', 'rows': public_rows})
                        save(output / 'results-private.json', {'status': 'running', 'manifest_sha256': manifest_digest,
                                                               'cases': [{k: v for k, v in item.items() if k != 'streams'} for item in cases], 'rows': private_rows})
                        print(json.dumps({k: row[k] for k in ('id', 'role', 'backend', 'extra_irq_cycles', 'flash_bytes', 'static_sram_bytes', 'full_pwm_exact', 'timing_admitted')}), flush=True)
        if sources() != frozen or sha(args.manifest.read_bytes()) != manifest_digest or source_hashes(ACTIVE / 'src') != baseline or source_hashes(derived) != patch_receipt['derived_source_sha256']:
            raise ValueError('Sources or manifest changed during final validation')
        # Re-read all bound segment files as well as the manifest itself.
        prepare(args.manifest)
        pairs = []
        for row in public_rows:
            if row['role'] != 'v6-repeat':
                continue
            before = next(r for r in public_rows if (r['id'], r['backend'], r['extra_irq_cycles'], r['role']) == (row['id'], row['backend'], row['extra_irq_cycles'], 'v5-control'))
            pairs.append({k: row[k] for k in ('id', 'group', 'profile', 'samples', 'segments', 'backend', 'extra_irq_cycles')} | {
                'data_saved_bytes': before['stream_bytes'] - row['stream_bytes'],
                'program_growth_bytes': row['program_flash_bytes'] - before['program_flash_bytes'],
                'net_full_flash_saved_bytes': before['flash_bytes'] - row['flash_bytes'],
                'static_sram_change_bytes': row['static_sram_bytes'] - before['static_sram_bytes'],
                'both_complete_pwm_exact': before['full_pwm_exact'] and row['full_pwm_exact'],
                'both_timing_admitted': before['timing_admitted'] and row['timing_admitted'],
                'stack_margin_change_bytes': row['report']['stack_margin_all_bytes'] - before['report']['stack_margin_all_bytes']})
        summary = {'schema': 'lpx-scale-repeat-player-pilot-v1', 'status': 'complete', 'seconds': time.perf_counter() - start,
                   'cases': len(cases), 'actual_complete_linked_images': len(public_rows), 'paired_controls': pairs,
                   'explicit_asm_images': sum(r['backend'] == 'explicit-avr-asm' for r in public_rows),
                   'asm_timing_admitted': sum(r['backend'] == 'explicit-avr-asm' and r['timing_admitted'] for r in public_rows),
                   'all_full_pwm_exact': all(r['full_pwm_exact'] for r in public_rows),
                   'all_images_fit32768': all(r['flash_within32768'] for r in public_rows),
                   'no_fit_or_dropped_cases': 0, 'production_sources_unchanged': True,
                   'quality_scope': 'Exact output only. No quality/audibility inference. C timing observations do not establish supported C real-time playback.'}
        save(output / 'rows.json', {'schema': 'lpx-scale-repeat-player-pilot-rows-v1', 'status': 'complete', 'rows': public_rows})
        save(output / 'results-private.json', {'status': 'complete', 'manifest_sha256': manifest_digest,
                                               'cases': [{k: v for k, v in item.items() if k != 'streams'} for item in cases], 'rows': private_rows})
        save(output / 'summary.json', summary)
        print(json.dumps({k: summary[k] for k in ('status', 'seconds', 'actual_complete_linked_images', 'asm_timing_admitted', 'all_full_pwm_exact')}), flush=True)
    finally:
        for session in old_sessions:
            session.__exit__()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    for name in ('avr-bin', 'include', 'lib'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--wsl')
    main(parser.parse_args())
