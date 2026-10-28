"""Validate frozen paired V5 assets with the current source epoch's player.

No encoder or quality selection runs here. Research gain/target distinctions
are carried through the private handoff and anonymous numeric projection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from admit import Epoch, canonical, sha


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def bound_entry(entry, epoch):
    if type(entry.get('samples')) is not int or entry['samples'] < 1 or entry.get('profile') not in (4, 6):
        raise ValueError('Invalid chain metadata')
    parts = entry.get('segments')
    if not isinstance(parts, list) or not 1 <= len(parts) <= 255:
        raise ValueError('Expected ordered reset segments')
    streams = []
    paths = []
    start = 0
    for number, part in enumerate(parts):
        path = Path(part['path']).resolve()
        blob = path.read_bytes()
        if part['index'] != number or part['start'] != start or sha(blob) != part['stream_sha256'] or len(blob) != part['file_bytes']:
            raise ValueError('Frozen stream identity or reset geometry changed')
        if not 1 <= len(blob) <= 65535:
            raise ValueError('Stream exceeds the existing ROM API')
        values = epoch.modules['speech_compact'].unpack(blob)
        if values[0] != part['samples'] or values[1] != entry['profile']:
            raise ValueError('Frozen stream header changed')
        start += values[0]
        streams.append(blob)
        paths.append(path)
    if start != entry['samples'] or sum(map(len, streams)) != entry['file_bytes']:
        raise ValueError('Complete chain totals changed')
    return streams, paths


def main(args):
    began = time.perf_counter()
    epoch = Epoch(args.source_root)
    output = epoch.output(args.output)
    handoff_bytes = args.handoff.read_bytes()
    prepared_bytes = args.prepared.read_bytes()
    handoff = json.loads(handoff_bytes)
    prepared = json.loads(prepared_bytes)
    if handoff.get('schema') != 'lpx-quiet-voice-player-pairs-private-v1' or Path(handoff['source_root']).resolve() != epoch.root:
        raise ValueError('Handoff belongs to a different protocol/source epoch')
    if handoff['preparation_sha256'] != sha(prepared_bytes) or Path(prepared['source_root']).resolve() != epoch.root:
        raise ValueError('Prepared source/toolchain/observer identity changed')
    if prepared['dispatcher_sha256'] != sha(Path(sys.modules['admit'].__file__).read_bytes()) or prepared['source_inventory'] != epoch.snapshot():
        raise ValueError('Prepared dispatcher or current source epoch changed')
    if prepared['decoder_source_sha256'] != epoch.bench.source_hashes(epoch.active / 'src'):
        raise ValueError('Frozen production decoder changed')
    pairs = handoff.get('pairs')
    if not isinstance(pairs, list) or not pairs or len({pair['id'] for pair in pairs}) != len(pairs):
        raise ValueError('Expected unique frozen pairs')
    for pair in pairs:
        if pair['reference_domain'] not in ('preserve-original', 'auto-declared-target') or type(pair['quality_adopted']) is not bool:
            raise ValueError('Explicit reference/quality role is required')
        if pair['reference_domain'] == 'auto-declared-target' and pair['quality_adopted']:
            raise ValueError('Optional auto research cannot be activated by playback validation')
        for key in ('old_playback_gain', 'new_input_gain'):
            if isinstance(pair[key], bool) or not isinstance(pair[key], (float, int)) or not math.isfinite(pair[key]) or pair[key] <= 0:
                raise ValueError('Explicit positive level metadata is required')
        if (pair['original']['samples'], pair['original']['profile']) != (pair['candidate']['samples'], pair['candidate']['profile']):
            raise ValueError('A paired comparison must retain sample/profile geometry')
    snapshot = epoch.snapshot()
    runner = Path(prepared['runner'])
    avr_bin = Path(prepared['avr_bin'])
    lib = Path(prepared['lib'])
    wsl = prepared['wsl']
    # Fresh host validation originates from this epoch, including this dispatcher.
    validation = epoch.bench.validation_provenance(runner, lib, wsl,
        sources=(Path(__file__), Path(sys.modules['admit'].__file__), epoch.player.VALIDATION / 'sim_player.c', epoch.player.VALIDATION / 'player_hardware.cpp'))
    if validation['runtime'] != prepared['validation']['runtime']:
        raise ValueError('Prepared observer/runtime dependencies changed')
    current_env = epoch.bench.environment(epoch.active, avr_bin, True, harness=epoch.player.EXAMPLE / 'player.cpp', required_symbols=(), retained_symbols=())
    if current_env['dependencies'] != prepared['build_environment']['dependencies'] or current_env['compile_source_sha256'] != prepared['build_environment']['compile_source_sha256']:
        raise ValueError('Prepared toolchain/compiled decoder dependencies changed')
    private = {'schema': 'lpx-quiet-voice-player-admission-private-v1', 'status': 'running',
               'handoff_sha256': sha(handoff_bytes), 'preparation_sha256': sha(prepared_bytes),
               'source_inventory': snapshot, 'target_dispatcher_sha256': sha(Path(__file__).read_bytes()),
               'validation': validation, 'rows': []}
    public = []
    global_inputs = [args.handoff, args.prepared, runner, Path(__file__), Path(sys.modules['admit'].__file__)]
    bound = {}
    for index, pair in enumerate(pairs):
        for role in ('original', 'candidate'):
            streams, paths = bound_entry(pair[role], epoch)
            bound[(index, role)] = streams
            global_inputs.extend(paths)
    outputs = [output / name for name in ('results-private.json', 'rows.json', 'summary.json', 'source-runtime.json')]
    epoch.modules['output_paths'].protect_outputs(global_inputs, outputs)
    import numpy as np
    sessions = [epoch.modules['batch_decoder'].BatchSession('batch', speech=True, speech_compact=True, compact_only=bool(only)) for only in (0, 1)]
    native = [session.__enter__() for session in sessions]
    try:
        for index, pair in enumerate(pairs):
            for role in ('original', 'candidate'):
                entry = pair[role]
                streams = bound[(index, role)]
                pcms = []
                pwms = []
                for blob in streams:
                    model = epoch.modules['speech_compact'].decode_model(blob)
                    n = int.from_bytes(blob[8:12], 'little')
                    expected = epoch.modules['standard_metrics'].pwm_duties(model)
                    for decoder in native:
                        np.testing.assert_array_equal(decoder.decode_one_s16(blob, n), model)
                        np.testing.assert_array_equal(decoder.decode_one(blob, n), expected)
                    pcms.append(model)
                    pwms.append(expected)
                expected = np.concatenate(pwms).tobytes()
                pcm_hash = sha(np.concatenate(pcms).astype('<i2').tobytes())
                if len(expected) != entry['samples']:
                    raise AssertionError('Complete reset chain output length changed')
                for key, actual in (('pcm16_sha256', pcm_hash), ('pwm_sha256', sha(expected))):
                    if key in entry and entry[key] != actual:
                        raise AssertionError('Frozen expected model output changed')
                for irq in prepared['irq_loads']:
                    if epoch.snapshot() != snapshot or args.handoff.read_bytes() != handoff_bytes or args.prepared.read_bytes() != prepared_bytes:
                        raise ValueError('Frozen sources/handoff/preparation changed during admission')
                    fresh, _ = bound_entry(entry, epoch)
                    if fresh != streams:
                        raise ValueError('Frozen chain changed during admission')
                    folder = output / 'images' / ('pair-%03d' % (index + 1)) / role / ('irq-' + str(irq))
                    epoch.player.guard(folder, global_inputs)
                    row = {'pair': 'pair-%03d' % (index + 1), 'role': role, 'profile': entry['profile'],
                           'samples': entry['samples'], 'segments': len(streams), 'stream_bytes': entry['file_bytes'],
                           'extra_irq_cycles': irq, 'reference_domain': pair['reference_domain'],
                           'old_playback_gain': pair['old_playback_gain'], 'new_input_gain': pair['new_input_gain'],
                           'quality_adopted': pair['quality_adopted'], 'current_model_common_compact_pcm_pwm_exact': True}
                    if entry['file_bytes'] > 32768:
                        row.update(status='no-fit-data-alone', passed=False, valid_sample_pwm_exact=None)
                        detail = None
                    else:
                        try:
                            detail = epoch.player.simulate(streams, folder, avr_bin, runner, source=epoch.active,
                                queue=256, prefill=192, irq=irq, assembly=True, lib=lib, wsl=wsl,
                                expected_pwm=expected, require_valid=False)
                        except RuntimeError:
                            error = (folder / 'compile.stderr.log').read_text(errors='replace') if (folder / 'compile.stderr.log').is_file() else ''
                            if re.search(r"(?:region.*text.*overflowed|will not fit in region.*text)", error, re.I):
                                row.update(status='no-fit-linked-flash', passed=False, valid_sample_pwm_exact=None)
                                detail = None
                            else:
                                raise
                        if detail is not None:
                            cost = detail['cost']
                            report = detail['report']
                            actual = (folder / 'valid.pcm8').read_bytes()
                            if cost['stream_sha256'] != [sha(blob) for blob in streams] or cost['stream_bytes'] != entry['file_bytes'] or cost['source_fingerprint'] != sha(epoch.bench.canonical(prepared['decoder_source_sha256'])):
                                raise AssertionError('Linked image is not bound to the frozen source/streams')
                            within = cost['flash_bytes'] <= 32768
                            passed = detail['passed'] and within
                            row.update(status='passed' if passed else ('no-fit-linked-flash' if not within else 'timing-or-output-failed'),
                                passed=passed, valid_sample_pwm_exact=actual == expected,
                                flash_bytes=cost['flash_bytes'], program_flash_bytes=cost['program_flash_bytes'],
                                static_sram_bytes=cost['static_sram_bytes'], data_bytes=cost['data_bytes'], bss_bytes=cost['bss_bytes'],
                                physical_pwm_exact=actual == expected and report['underruns'] == 0 and report['timer_ticks'] == entry['samples'],
                                report=report)
                    public.append(row)
                    private['rows'].append({**row, 'handoff_pair_id': pair['id'], 'output': str(folder),
                        'streams_sha256': [sha(blob) for blob in streams], 'model_pcm16_sha256': pcm_hash,
                        'model_pwm_sha256': sha(expected), 'verification': detail})
                    epoch.save(output / 'rows.json', {'schema': 'lpx-quiet-voice-player-rows-v1', 'status': 'running', 'rows': public})
                    epoch.save(output / 'results-private.json', private)
                    print(json.dumps({k: row[k] for k in ('pair', 'role', 'extra_irq_cycles', 'stream_bytes', 'status', 'passed')}), flush=True)
        if epoch.snapshot() != snapshot or args.handoff.read_bytes() != handoff_bytes or args.prepared.read_bytes() != prepared_bytes:
            raise ValueError('Source/asset binding changed at final checkpoint')
        for pair in pairs:
            for role in ('original', 'candidate'):
                bound_entry(pair[role], epoch)
        paired = []
        for index, pair in enumerate(pairs):
            for irq in prepared['irq_loads']:
                before = next(r for r in public if r['pair'] == 'pair-%03d' % (index + 1) and r['role'] == 'original' and r['extra_irq_cycles'] == irq)
                after = next(r for r in public if r['pair'] == before['pair'] and r['role'] == 'candidate' and r['extra_irq_cycles'] == irq)
                paired.append({'pair': before['pair'], 'extra_irq_cycles': irq, 'reference_domain': pair['reference_domain'],
                    'old_playback_gain': pair['old_playback_gain'], 'new_input_gain': pair['new_input_gain'],
                    'quality_adopted': pair['quality_adopted'], 'data_saved_bytes': before['stream_bytes'] - after['stream_bytes'],
                    'both_passed': before['passed'] and after['passed'],
                    'complete_flash_saved_bytes': None if 'flash_bytes' not in before or 'flash_bytes' not in after else before['flash_bytes'] - after['flash_bytes'],
                    'program_flash_change_bytes': None if 'program_flash_bytes' not in before or 'program_flash_bytes' not in after else after['program_flash_bytes'] - before['program_flash_bytes'],
                    'static_sram_change_bytes': None if 'static_sram_bytes' not in before or 'static_sram_bytes' not in after else after['static_sram_bytes'] - before['static_sram_bytes']})
        summary = {'schema': 'lpx-quiet-voice-player-admission-v1', 'status': 'complete', 'pairs': len(pairs),
                   'rows': len(public), 'linked_images': sum('flash_bytes' in r for r in public),
                   'passed': sum(r['passed'] for r in public), 'no_fit': sum(r['status'].startswith('no-fit') for r in public),
                   'timing_or_output_failures': sum(r['status'] == 'timing-or-output-failed' for r in public),
                   'paired': paired, 'seconds': time.perf_counter() - began, 'source_epoch_unchanged': True,
                   'quality_or_default_promoted_by_playback': False,
                   'scope': 'Current-source production-player validation only. Explicit input/playback gain and declared-target distinctions remain. No original-level quality, audibility, optional-auto default, or C real-time claim.'}
        public_binding = {'schema': 'lpx-quiet-voice-player-provenance-v1',
            'source_commit_at_prepare': prepared['source_commit_at_prepare'],
            'source_inventory': snapshot, 'decoder_source_sha256': prepared['decoder_source_sha256'],
            'compiler': current_env['compiler'], 'dependencies': current_env['dependencies'],
            'harness_sha256': current_env['harness_sha256'], 'compile_source_sha256': current_env['compile_source_sha256'],
            'validation': validation, 'dispatcher_sources_sha256': {'admit.py': sha(Path(sys.modules['admit'].__file__).read_bytes()), 'target.py': sha(Path(__file__).read_bytes())},
            'queue': 256, 'prefill': 192, 'extra_irq_cycles': prepared['irq_loads'], 'explicit_assembly': True,
            'physical_board_measured': False, 'private_asset_bindings_exported': False}
        private.update(status='complete', seconds=summary['seconds'])
        epoch.save(output / 'source-runtime.json', public_binding)
        epoch.save(output / 'rows.json', {'schema': 'lpx-quiet-voice-player-rows-v1', 'status': 'complete', 'rows': public})
        epoch.save(output / 'results-private.json', private)
        epoch.save(output / 'summary.json', summary)
        print(json.dumps({k: summary[k] for k in ('status', 'rows', 'linked_images', 'passed', 'no_fit', 'timing_or_output_failures', 'seconds')}), flush=True)
    finally:
        for session in sessions:
            session.__exit__()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
