"""Admit existing bounded adaptive target winners; no fitting or quality adoption."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from admit import Epoch, sha
from player_evidence import PlayerEvidence


def main(args):
    began = time.perf_counter()
    epoch = Epoch(args.source_root)
    prepared_raw = args.prepared.read_bytes(); prepared = json.loads(prepared_raw)
    assert prepared['source_inventory'] == epoch.snapshot() and Path(prepared['source_root']).resolve() == epoch.root
    assert prepared['dispatcher_sha256'] == sha(Path(sys.modules['admit'].__file__).read_bytes())
    proof = PlayerEvidence(epoch, prepared)
    out = epoch.output(args.output)
    producer_raw = (args.producer / 'binding-private.json').read_bytes()
    producer = json.loads(producer_raw)
    assert producer['head'] == '5a6cd1ab9593cac6f7e81756a639fa11d6c21276'
    assert producer['gain'] == 64 and producer['samples'] == 32000
    assert producer['caps'] == [1800, 1930, 2060] and producer['no_new_seed_fits']
    assert not producer['listening_adoption']
    import soundfile as sf
    reference, rate = sf.read(args.reference, dtype='int16')
    assert rate == 8000 and reference.shape == (32000,)
    assert sha(reference.astype('<i2').tobytes()) == producer['target_sha256']
    producer_pins = {str((args.producer / 'binding-private.json').resolve()): sha(producer_raw),
                     str(args.reference.resolve()): sha(args.reference.read_bytes())}
    names = {'baseline': args.baseline}
    for value in args.candidate:
        label, path = value.split('=', 1)
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}', label) or label in names:
            raise ValueError('Expected unique generic variant labels')
        names[label] = Path(path)
    assert len(names) == 4 and args.input_gain == 64
    frozen = []
    for label, path in names.items():
        blob = path.read_bytes(); values = epoch.modules['speech_compact'].unpack(blob)
        assert values[:2] == (32000, 4) and len(blob) <= 65535
        if label == 'baseline':
            assert sha(blob) == producer['control_sha256']
        else:
            marker_path, report_path = path.parent / 'complete-private.json', path.parent / 'report-private.json'
            marker, report = json.loads(marker_path.read_bytes()), json.loads(report_path.read_bytes())
            assert marker['status'] == 'complete' and marker['guard_pass']
            assert marker['selected_sha256'] == sha(blob)
            assert report['schema'] == 'lpx-v5-adaptive-voice-v2' and report['samples'] == 32000 and report['profile'] == 4
            assert report['selected_bytes'] == len(blob) and report['native_common_and_model_exact'] and report['native_v5_only_checked']
            assert report['refinement_calls'] == report['max_refinement_calls'] == 4
            assert report['complete_byte_cap'] in producer['caps'] and len(blob) <= report['complete_byte_cap']
            assert report['candidates'][report['selected_id']]['file_bytes'] == len(blob)
            for item in (marker_path, report_path):producer_pins[str(item.resolve())] = sha(item.read_bytes())
        frozen.append({'variant': label, 'path': str(path.resolve()), 'stream_sha256': sha(blob), 'file_bytes': len(blob), 'samples': values[0], 'profile': values[1]})
    assert frozen[0]['file_bytes'] == 1702
    assert len({item['stream_sha256'] for item in frozen}) == 4
    handoff = {'schema': 'lpx-adaptive-target-player-input-private-v1', 'source_root': str(epoch.root),
        'preparation_sha256': sha(prepared_raw), 'variants': frozen, 'declared_input_gain': args.input_gain,
        'reference_domain': 'declared-gain64-target1702', 'quality_adopted': False, 'new_fits': 0,
        'producer_inputs': producer_pins, 'producer_core_commit': producer['head'],
        'scope': 'Existing adaptive candidates; playback validation does not adopt them or establish quality. A/B listening was inconclusive.'}
    target = out / 'inputs-private.json'
    if target.exists():
        assert json.loads(target.read_text()) == handoff
    else:
        epoch.save(target, handoff)
    native_binding = json.loads((args.study / 'binding-private.json').read_text())
    for name, digest in native_binding['source']['core'].items():
        assert sha((epoch.root / name).read_bytes()) == digest
    for name, digest in native_binding['native_libraries_sha256'].items():
        assert sha((args.study / 'native' / name).read_bytes()) == digest
    prior = json.loads((args.prior / 'results-private.json').read_text())
    assert prior['status'] == 'complete'
    index = {}
    for row in prior['rows']:
        key = (tuple(row['stream_sha256']), row['extra_irq_cycles'])
        assert key not in index; index[key] = row
    import numpy as np
    sessions = [epoch.modules['batch_decoder'].BatchSession('batch', prebuilt=args.study / 'native' / name) for name in ('common.so', 'v5-only.so')]
    decoders = [s.__enter__() for s in sessions]
    snapshot = epoch.snapshot(); rows = []; private = []
    inputs = [args.prepared, args.prior / 'results-private.json', args.study / 'binding-private.json', *names.values(), *map(Path, producer_pins), Path(__file__), Path(sys.modules['admit'].__file__), Path(sys.modules['player_evidence'].__file__)]
    epoch.modules['output_paths'].protect_outputs(inputs, [out / name for name in ('rows.json', 'summary.json', 'results-private.json', 'source-runtime.json')])
    attempt_path = out / 'attempt-private.json'
    if attempt_path.exists():
        raise ValueError('Preserve existing campaign attempts; use an explicit audited resume')
    attempt = {'status': 'running', 'source_inventory': snapshot, 'images': [], 'new_fits': 0, 'started_unix_ns': time.time_ns()}
    epoch.save(attempt_path, attempt)
    try:
        for variant in frozen:
            blob = Path(variant['path']).read_bytes(); assert sha(blob) == variant['stream_sha256']
            pcm = epoch.modules['speech_compact'].decode_model(blob)
            pwm = epoch.modules['standard_metrics'].pwm_duties(pcm)
            for decoder in decoders:
                np.testing.assert_array_equal(decoder.decode_one_s16(blob, 32000), pcm)
                np.testing.assert_array_equal(decoder.decode_one(blob, 32000), pwm)
            expected = pwm.tobytes()
            for irq in (0, 100):
                assert epoch.snapshot() == snapshot and args.prepared.read_bytes() == prepared_raw
                for name, digest in producer_pins.items():assert sha(Path(name).read_bytes()) == digest
                assert sha(Path(variant['path']).read_bytes()) == variant['stream_sha256']
                old = index.get(((variant['stream_sha256'],), irq))
                event = {'variant': variant['variant'], 'extra_irq_cycles': irq, 'stream_bytes': len(blob),
                         'status': 'running', 'expected_prior_reuse': old is not None, 'started_unix_ns': time.time_ns()}
                attempt['images'].append(event); epoch.save(attempt_path, attempt)
                result = None; reused = False; status = None
                folder = out / 'images' / variant['variant'] / ('irq-' + str(irq))
                if len(blob) > 32768:
                    status = 'no-fit-data-alone'
                elif old is not None:
                    result, folder = proof.reuse(old, [blob], expected, irq); reused = True
                else:
                    epoch.player.guard(folder, inputs)
                    try:
                        result = epoch.player.simulate([blob], folder, proof.avr, proof.runner, source=epoch.active,
                            queue=256, prefill=192, irq=irq, assembly=True, lib=proof.lib, wsl=proof.wsl, expected_pwm=expected, require_valid=False)
                    except RuntimeError:
                        text = (folder / 'compile.stderr.log').read_text(errors='replace') if (folder / 'compile.stderr.log').is_file() else ''
                        if re.search(r'(?:region.*text.*overflowed|will not fit in region.*text)', text, re.I):status = 'no-fit-linked-flash'
                        else:raise
                row = {'variant': variant['variant'], 'profile': 4, 'samples': 32000, 'stream_bytes': len(blob),
                    'extra_irq_cycles': irq, 'declared_input_gain': args.input_gain, 'reference_domain': handoff['reference_domain'],
                    'exploratory': variant['variant'] != 'baseline', 'quality_adopted': False, 'quality_measured_here': False,
                    'model_common_compact_pcm_pwm_exact': True, 'reused_frozen_image': reused,
                    'new_unique_image_for_campaign': result is not None and not reused, 'status': status, 'passed': False}
                if result is not None:
                    cost, report = result['cost'], result['report']; proof.verify_recipe(cost, [blob], irq)
                    actual = (folder / 'valid.pcm8').read_bytes(); within = cost['flash_bytes'] <= 32768
                    passed = result['passed'] and within
                    row.update(status='passed' if passed else ('no-fit-linked-flash' if not within else 'timing-or-output-failed'), passed=passed,
                        flash_bytes=cost['flash_bytes'], program_flash_bytes=cost['program_flash_bytes'],
                        static_sram_bytes=cost['static_sram_bytes'], data_bytes=cost['data_bytes'], bss_bytes=cost['bss_bytes'],
                        physical_pwm_exact=actual == expected and report['underruns'] == 0 and report['timer_ticks'] == 32000, report=report)
                rows.append(row)
                event.update({k: row[k] for k in ('variant', 'extra_irq_cycles', 'stream_bytes', 'status', 'reused_frozen_image')})
                event['ended_unix_ns'] = time.time_ns()
                epoch.save(attempt_path, attempt)
                private.append({**row, 'path': variant['path'], 'stream_sha256': [variant['stream_sha256']], 'output': str(folder),
                    'pcm16_sha256': sha(pcm.astype('<i2').tobytes()), 'pwm_sha256': sha(expected), 'verification': result})
                epoch.save(out / 'rows.json', {'status': 'running', 'rows': rows})
                epoch.save(out / 'results-private.json', {'schema': 'lpx-adaptive-target-player-private-v1', 'status': 'running', 'inputs': handoff, 'rows': private})
                print(json.dumps({key: row[key] for key in ('variant', 'extra_irq_cycles', 'stream_bytes', 'status', 'reused_frozen_image')}), flush=True)
        assert epoch.snapshot() == snapshot
        for name, digest in producer_pins.items():assert sha(Path(name).read_bytes()) == digest
        for variant in frozen:assert sha(Path(variant['path']).read_bytes()) == variant['stream_sha256']
        paired = []
        for label in names:
            if label == 'baseline':continue
            for irq in (0, 100):
                before = next(r for r in rows if r['variant'] == 'baseline' and r['extra_irq_cycles'] == irq)
                after = next(r for r in rows if r['variant'] == label and r['extra_irq_cycles'] == irq)
                paired.append({'variant': label, 'extra_irq_cycles': irq, 'data_growth_bytes': after['stream_bytes'] - before['stream_bytes'],
                    'full_flash_growth_bytes': None if 'flash_bytes' not in before or 'flash_bytes' not in after else after['flash_bytes'] - before['flash_bytes'],
                    'program_flash_change_bytes': None if 'program_flash_bytes' not in before or 'program_flash_bytes' not in after else after['program_flash_bytes'] - before['program_flash_bytes'],
                    'both_passed': before['passed'] and after['passed'], 'exploratory_not_adopted': True})
        summary = {'schema': 'lpx-adaptive-target-player-admission-v1', 'status': 'complete', 'variants': 4, 'rows': len(rows),
            'passed': sum(r['passed'] for r in rows), 'new_unique_images_for_campaign': sum(r['new_unique_image_for_campaign'] for r in rows),
            'reused_frozen_images': sum(r['reused_frozen_image'] for r in rows), 'no_fit': sum(r['status'].startswith('no-fit') for r in rows),
            'timing_or_output_failures': sum(r['status'] == 'timing-or-output-failed' for r in rows), 'comparisons': paired,
            'declared_input_gain': 64, 'source_commit': native_binding['core_commit'], 'source_epoch_unchanged': True,
            'producer_core_commit': producer['head'], 'target_candidate_stream_bytes': [item['file_bytes'] for item in frozen[1:]],
            'new_fits': 0, 'quality_adopted': False, 'seconds': time.perf_counter() - began,
            'scope': 'Existing adaptive target winners versus exact target1702 baseline at declared gain64. Playback/size only; A/B preference inconclusive. No original-level quality, audibility, policy or C real-time claim.'}
        sources = {p.name: sha(p.read_bytes()) for p in (Path(__file__), Path(sys.modules['admit'].__file__), Path(sys.modules['player_evidence'].__file__))}
        provenance = {'schema': 'lpx-adaptive-target-player-source-v1', 'source_commit': native_binding['core_commit'], 'source_inventory': snapshot,
            'producer_core_commit': producer['head'],
            'decoder_source_sha256': proof.env['source_sha256'], 'compiler': proof.env['compiler'], 'dependencies': proof.env['dependencies'],
            'compile_source_sha256': proof.env['compile_source_sha256'], 'harness_sha256': proof.env['harness_sha256'],
            'validation': proof.validation, 'sources_sha256': sources, 'compiler_options_by_irq': {str(irq): proof.recipe([blob], irq)[2] for irq in (0, 100)},
            'queue': 256, 'prefill': 192, 'explicit_asm': True, 'private_media_or_image_fingerprints_exported': False}
        epoch.save(out / 'source-runtime.json', provenance)
        epoch.save(out / 'rows.json', {'schema': 'lpx-adaptive-target-player-rows-v1', 'status': 'complete', 'rows': rows})
        epoch.save(out / 'results-private.json', {'schema': 'lpx-adaptive-target-player-private-v1', 'status': 'complete', 'inputs': handoff, 'rows': private, 'summary': summary})
        epoch.save(out / 'summary.json', summary)
        attempt.update(status='complete', ended_unix_ns=time.time_ns())
        epoch.save(attempt_path, attempt)
        print(json.dumps({k: summary[k] for k in ('status', 'rows', 'passed', 'new_unique_images_for_campaign', 'reused_frozen_images', 'no_fit', 'timing_or_output_failures', 'seconds')}), flush=True)
    except Exception as exc:
        attempt.update(status='failed', exception_type=type(exc).__name__, ended_unix_ns=time.time_ns())
        epoch.save(attempt_path, attempt)
        epoch.save(out / 'failure-private.json', {'exception_type': type(exc).__name__, 'traceback': traceback.format_exc()})
        print(json.dumps({'status': 'failed', 'exception_type': type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
    finally:
        for session in sessions:session.__exit__()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'prepared', 'study', 'prior', 'baseline', 'producer', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate', action='append', required=True)
    parser.add_argument('--input-gain', type=int, required=True)
    main(parser.parse_args())
