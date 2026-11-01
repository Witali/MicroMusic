"""Admit the audited exact-chain union, proving frozen-image reuse read only."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from admit import Epoch, canonical, sha
from target import bound_entry


def load(path):
    return json.loads(Path(path).read_text())


def main(args):
    started = time.perf_counter()
    epoch = Epoch(args.source_root)
    raw = args.handoff.read_bytes(); union = json.loads(raw)
    prepared_raw = args.prepared.read_bytes(); prepared = json.loads(prepared_raw)
    assert union['schema'] == 'lpx-quiet-voice-player-union-private-v1'
    assert Path(union['source_root']).resolve() == epoch.root and union['preparation_sha256'] == sha(prepared_raw)
    assert epoch.snapshot() == prepared['source_inventory'] == union['source_inventory']
    assert sha((args.audit / 'audit.json').read_bytes()) == union['audit_sha256']
    assert sha((args.audit / 'context-audit.json').read_bytes()) == union['context_audit_sha256']
    assert sha((args.audit / 'audit-private.json').read_bytes()) == union['audit_private_sha256']
    binding = load(args.study / 'binding-private.json')
    assert sha((args.study / 'binding-private.json').read_bytes()) == union['study_binding_sha256']
    for name, digest in binding['native_libraries_sha256'].items():
        assert sha((args.study / 'native' / name).read_bytes()) == digest
    snapshot = epoch.snapshot()
    folder = epoch.output(args.output)
    avr, runner, lib = map(Path, (prepared['avr_bin'], prepared['runner'], prepared['lib']))
    wsl = prepared['wsl']
    bench, player = epoch.bench, epoch.player
    validation = bench.validation_provenance(runner, lib, wsl,
        sources=(Path(player.__file__), player.VALIDATION / 'sim_player.c', player.VALIDATION / 'player_hardware.cpp', player.EXAMPLE / 'player_config.h'))
    validation['runner_sources'] = {'sim_player.c': bench.digest(player.VALIDATION / 'sim_player.c')}
    assert validation['runtime'] == prepared['validation']['runtime']
    env = bench.environment(epoch.active, avr, True, harness=player.EXAMPLE / 'player.cpp', required_symbols=(), retained_symbols=())
    env['settings'] = {**env['settings'], 'queue': 256, 'prefill': 192}
    assert env['dependencies'] == prepared['build_environment']['dependencies']
    from measure_speech_firmware import voice_header
    proof = sha(bench.canonical([bench.artifact_provenance(avr), bench.digest(Path(player.__file__))]))
    def expected_build(streams, irq):
        flags = bench.command_flags(env, bench.CANDIDATES['unroll1-tune0-lto-call-relax'], True, irq)
        flags = [f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=', '-DLPX4_PROFILE_PREFILL=', '-DLPX4_PROFILE_IRQ_LOAD='))]
        flags += ['-DLPX_PLAYER_QUEUE=256', '-DLPX_PLAYER_PREFILL=192', '-DLPX_PLAYER_IRQ_LOAD=' + str(irq), '-DLPX_PLAYER_DATA_HEADER="voice_data.h"']
        suffix = '#define LPX_PLAYER_SEGMENTS %d\n' % len(streams)
        header = voice_header(streams).replace('profile_', 'lpx_') + suffix
        layout = voice_header([b'' for _ in streams]).replace('profile_', 'lpx_') + suffix
        recipe = {'environment': bench.build_provenance(env), 'compiler_options': flags,
            'player_config_sha256': bench.digest(player.EXAMPLE / 'player_config.h'), 'voice_layout_sha256': sha(layout.encode()),
            'declared_segment_samples': [int.from_bytes(b[8:12], 'little') for b in streams]}
        build_id = sha(bench.canonical(recipe))
        image_id = sha(bench.canonical([build_id, [sha(b) for b in streams], sha(header.encode())]))
        return build_id, image_id, flags
    # Prior evidence is immutable; no builder/simulator call touches its folder.
    prior = load(args.prior / 'results-private.json')
    prior_index = {}
    assert prior['status'] == 'complete'
    for old in prior['rows']:
        key = (tuple(old['streams_sha256']), old['extra_irq_cycles'])
        assert key not in prior_index
        prior_index[key] = old
    def reuse(old, streams, expected, irq):
        directory = Path(old['output'])
        cost_cache = load(directory / 'cost.json'); verified = load(directory / 'verification.json')
        cost = cost_cache['cost']
        build_id, image_id, flags = expected_build(streams, irq)
        assert cost_cache['fingerprint'] == image_id and cost_cache['proof_fingerprint'] == proof
        assert cost_cache['cost_sha256'] == sha(bench.canonical(cost))
        assert cost['build_fingerprint'] == build_id and cost['compiler_options'] == flags
        assert cost['source_fingerprint'] == sha(bench.canonical(env['source_sha256']))
        assert cost['environment'] == env and cost['stream_sha256'] == [sha(b) for b in streams]
        assert cost == verified['cost'] == old['verification']['cost']
        for name, key in (('player.elf', 'image_sha256'), ('program.bin', 'binary_sha256'), ('player.hex', 'hex_sha256')):
            assert bench.digest(directory / name) == cost[key]
        player.checked_image(directory, avr, streams, 256)
        assert verified['validation_provenance'] == validation
        expected_fingerprint = sha(bench.canonical([validation, cost['image_sha256'], bench.digest(directory / 'observer.txt'), sha(expected), 0]))
        assert verified['fingerprint'] == expected_fingerprint
        report = load(directory / 'observer.json'); actual = (directory / 'valid.pcm8').read_bytes()
        assert bench.digest(directory / 'observer.json') == verified['report_sha256'] and sha(actual) == verified['pwm_sha256']
        assert report == verified['report'] and actual == expected
        assert player.validate(report, actual, expected) and verified['passed'] and cost['flash_bytes'] <= 32768
        return verified, directory
    inputs = [args.handoff, args.prepared, args.study / 'binding-private.json', args.audit / 'audit-private.json', args.prior / 'results-private.json', runner,
              Path(__file__), Path(sys.modules['admit'].__file__), Path(sys.modules['target'].__file__)]
    chains = {}
    for item in union['chains']:
        streams, paths = bound_entry(item['entry'], epoch)
        chains[item['id']] = streams; inputs.extend(paths)
    epoch.modules['output_paths'].protect_outputs(inputs, [folder / name for name in ('results-private.json', 'rows.json', 'summary.json', 'source-runtime.json')])
    import numpy as np
    sessions = [epoch.modules['batch_decoder'].BatchSession('batch', prebuilt=args.study / 'native' / name) for name in ('common.so', 'v5-only.so')]
    native = [s.__enter__() for s in sessions]
    public = []; private = []
    try:
        for item in union['chains']:
            entry = item['entry']; streams = chains[item['id']]
            pcm_parts = []
            for blob in streams:
                pcm = epoch.modules['speech_compact'].decode_model(blob)
                pwm = epoch.modules['standard_metrics'].pwm_duties(pcm)
                for decoder in native:
                    np.testing.assert_array_equal(decoder.decode_one_s16(blob, len(pcm)), pcm)
                    np.testing.assert_array_equal(decoder.decode_one(blob, len(pcm)), pwm)
                pcm_parts.append(pcm)
            pcm = np.concatenate(pcm_parts); expected = epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes()
            assert sha(pcm.astype('<i2').tobytes()) == entry['pcm16_sha256'] and sha(expected) == entry['pwm_sha256']
            for irq in (0, 100):
                assert epoch.snapshot() == snapshot and args.handoff.read_bytes() == raw and args.prepared.read_bytes() == prepared_raw
                assert bound_entry(entry, epoch)[0] == streams
                key = (tuple(sha(b) for b in streams), irq)
                old = prior_index.get(key)
                result = None; reused = False; status = None
                output = folder / 'images' / item['id'] / ('irq-' + str(irq))
                if entry['file_bytes'] > 32768:
                    status = 'no-fit-data-alone'
                elif old is not None:
                    result, output = reuse(old, streams, expected, irq); reused = True
                else:
                    player.guard(output, inputs)
                    try:
                        result = player.simulate(streams, output, avr, runner, source=epoch.active,
                            queue=256, prefill=192, irq=irq, assembly=True, lib=lib, wsl=wsl, expected_pwm=expected, require_valid=False)
                    except RuntimeError:
                        text = (output / 'compile.stderr.log').read_text(errors='replace') if (output / 'compile.stderr.log').is_file() else ''
                        if re.search(r'(?:region.*text.*overflowed|will not fit in region.*text)', text, re.I):
                            status = 'no-fit-linked-flash'
                        else:
                            raise
                row = {'chain': item['id'], 'roles': item['roles'], 'profile': entry['profile'], 'samples': entry['samples'],
                    'segments': len(streams), 'stream_bytes': entry['file_bytes'], 'extra_irq_cycles': irq,
                    'reused_frozen_image': reused, 'newly_built_and_simulated': result is not None and not reused,
                    'model_common_compact_pcm_pwm_exact': True, 'status': status, 'passed': False}
                if result is not None:
                    cost, report = result['cost'], result['report']; actual = (output / 'valid.pcm8').read_bytes()
                    build_id, _, flags = expected_build(streams, irq)
                    assert cost['build_fingerprint'] == build_id and cost['compiler_options'] == flags
                    assert cost['stream_sha256'] == [sha(b) for b in streams] and cost['source_fingerprint'] == sha(bench.canonical(env['source_sha256']))
                    within = cost['flash_bytes'] <= 32768
                    passed = result['passed'] and within
                    row.update(status='passed' if passed else ('no-fit-linked-flash' if not within else 'timing-or-output-failed'), passed=passed,
                        flash_bytes=cost['flash_bytes'], program_flash_bytes=cost['program_flash_bytes'], static_sram_bytes=cost['static_sram_bytes'],
                        data_bytes=cost['data_bytes'], bss_bytes=cost['bss_bytes'], report=report,
                        physical_pwm_exact=actual == expected and report['underruns'] == 0 and report['timer_ticks'] == entry['samples'])
                public.append(row)
                private.append({**row, 'output': str(output), 'stream_sha256': [sha(b) for b in streams],
                    'pcm16_sha256': entry['pcm16_sha256'], 'pwm_sha256': entry['pwm_sha256'], 'verification': result,
                    'reuse_scope': 'Existing frozen research measurement labels remain immutable; only exact source/build/data/runtime identity is reused.' if reused else None})
                epoch.save(folder / 'rows.json', {'status': 'running', 'rows': public})
                epoch.save(folder / 'results-private.json', {'schema': 'lpx-quiet-voice-v1-player-union-results-private-v1', 'status': 'running',
                    'handoff_sha256': sha(raw), 'rows': private, 'comparisons': union['comparisons']})
                print(json.dumps({k: row[k] for k in ('chain', 'extra_irq_cycles', 'status', 'reused_frozen_image', 'newly_built_and_simulated')}), flush=True)
        assert epoch.snapshot() == snapshot and args.handoff.read_bytes() == raw
        paired = []
        for comparison in union['comparisons']:
            for irq in (0, 100):
                old = next(r for r in public if r['chain'] == comparison['original_chain'] and r['extra_irq_cycles'] == irq)
                new = next(r for r in public if r['chain'] == comparison['candidate_chain'] and r['extra_irq_cycles'] == irq)
                item = {k: comparison[k] for k in ('id', 'profile', 'mode', 'reference_domain', 'old_playback_gain', 'new_input_gain', 'quality_adopted_at_frozen_study', 'eligible_under_frozen_whole_chain_gates', 'changed_from_declared_target_control')}
                item.update(extra_irq_cycles=irq, cap_percents=sorted(s['percent'] for s in comparison['selections']),
                    targeted_not_independent_heldout=any(s['targeted'] for s in comparison['selections']),
                    original_stream_bytes=old['stream_bytes'], candidate_stream_bytes=new['stream_bytes'],
                    both_passed=old['passed'] and new['passed'], data_saved_bytes=old['stream_bytes'] - new['stream_bytes'],
                    complete_flash_saved_bytes=None if 'flash_bytes' not in old or 'flash_bytes' not in new else old['flash_bytes'] - new['flash_bytes'],
                    program_flash_change_bytes=None if 'program_flash_bytes' not in old or 'program_flash_bytes' not in new else new['program_flash_bytes'] - old['program_flash_bytes'])
                paired.append(item)
        summary = {'schema': 'lpx-quiet-voice-v1-player-union-v1', 'status': 'complete', 'unique_chains': len(union['chains']),
            'unique_changed_selected_candidate_chains': sum('changed-selected-candidate' in c['roles'] for c in union['chains']),
            'distinct_original_level_control_chains': sum('original-level-control' in c['roles'] for c in union['chains']),
            'changed_selection_rows_covered': union['changed_selection_rows'], 'unchanged_selected_rows_not_remeasured': union['unchanged_selected_rows_not_measured'],
            'rows': len(public), 'passed': sum(r['passed'] for r in public), 'newly_built_and_simulated_images': sum(r['newly_built_and_simulated'] for r in public),
            'reused_frozen_images': sum(r['reused_frozen_image'] for r in public), 'no_fit': sum(r['status'].startswith('no-fit') for r in public),
            'timing_or_output_failures': sum(r['status'] == 'timing-or-output-failed' for r in public), 'comparisons': paired,
            'seconds': time.perf_counter() - started, 'source_epoch_unchanged': True,
            'scope': 'Exact chain deduplication and actual complete-player admission only. Preserve/auto, gain, targeted and frozen whole-gate domains stay explicit. Prior measurement labels are immutable. No fit, policy or original-level quality promotion.'}
        source = {'schema': 'lpx-quiet-voice-v1-player-provenance-v1', 'source_commit': binding['core_commit'],
            'source_inventory': snapshot, 'decoder_source_sha256': env['source_sha256'], 'compiler': env['compiler'], 'dependencies': env['dependencies'],
            'compile_source_sha256': env['compile_source_sha256'], 'harness_sha256': env['harness_sha256'], 'validation': validation,
            'sources_sha256': {p.name: sha(p.read_bytes()) for p in (Path(__file__), Path(sys.modules['admit'].__file__), Path(sys.modules['target'].__file__))},
            'compiler_options_by_irq': {str(irq): expected_build(chains[union['chains'][0]['id']], irq)[2] for irq in (0, 100)},
            'reuse_proof': 'Exact current build recipe/fingerprint, source/header/toolchain/harness, ordered embedded bytes, ELF/binary/HEX, symbol/observer metadata fingerprint, model expectation, runtime, report, physical PWM and strict validator; original evidence is read only.',
            'queue': 256, 'prefill': 192, 'explicit_asm': True, 'private_asset_bindings_exported': False}
        epoch.save(folder / 'source-runtime.json', source)
        epoch.save(folder / 'rows.json', {'schema': 'lpx-quiet-voice-v1-player-union-rows-v1', 'status': 'complete', 'rows': public})
        epoch.save(folder / 'results-private.json', {'schema': 'lpx-quiet-voice-v1-player-union-results-private-v1', 'status': 'complete',
            'handoff_sha256': sha(raw), 'rows': private, 'comparisons': union['comparisons'], 'summary': summary})
        epoch.save(folder / 'summary.json', summary)
        print(json.dumps({k: summary[k] for k in ('status', 'rows', 'passed', 'newly_built_and_simulated_images', 'reused_frozen_images', 'no_fit', 'timing_or_output_failures', 'seconds')}), flush=True)
    finally:
        for session in sessions:
            session.__exit__()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'study', 'audit', 'handoff', 'prepared', 'prior', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
