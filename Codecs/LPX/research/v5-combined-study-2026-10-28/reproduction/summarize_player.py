"""Recheck private player artifacts and export anonymous source-bound numbers."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from build_release_player import validate
import speech_compact as compact
from standard_metrics import pwm_duties


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(study, output):
    root = Path.cwd()
    study = study.resolve()
    assert study.is_relative_to((root / 'build').resolve())
    player = study / 'player'
    binding_data = (player / 'bindings-private.json').read_bytes()
    binding = json.loads(binding_data)
    workers = [json.loads((player / f'shard-{s}-private.json').read_text()) for s in (0, 1)]
    assert all(w['status'] == 'complete' for w in workers)
    assert all(w['bindings_sha256'] == sha(binding_data) for w in workers)
    driver = Path(__file__).with_name('admit_player.py')
    assert all(w['script_sha256'] == sha(driver.read_bytes()) for w in workers)
    source = workers[0]['source_sha256']
    assert all(w['source_sha256'] == source for w in workers)
    assert all(sha((root / path).read_bytes()) == digest for path, digest in source.items())
    for path, digest in binding['study_inputs'].items():
        assert sha(Path(path).read_bytes()) == digest
    assert sha((study / 'audit-anonymous.json').read_bytes()) == binding['audit_sha256']
    original_paths = [player / f'original-shard-{s}-private.json' for s in (0, 1)]
    cached_revalidation = all(path.is_file() for path in original_paths)
    original_runs = [json.loads(path.read_text()) for path in original_paths] if cached_revalidation else workers
    assert all(old['status'] == 'complete' and old['rows'] == new['rows']
               for old, new in zip(original_runs, workers))
    raw_rows = [r for w in workers for r in w['rows']]
    by_key = {(r['chain_id'], r['irq']): r['result'] for r in raw_rows}
    assert len(by_key) == 2 * len(binding['chains'])
    chains = {c['id']: c for c in binding['chains']}
    rows = []
    provenance = raw_rows[0]['result']['validation_provenance']
    environment = raw_rows[0]['result']['cost']['environment']
    numeric_cost = ('stream_bytes', 'segments', 'samples', 'flash_bytes', 'program_flash_bytes',
                    'text_bytes', 'data_bytes', 'bss_bytes', 'static_sram_bytes',
                    'queue', 'prefill', 'index_bytes', 'extra_irq_cycles')
    for chain_id, chain in chains.items():
        blobs = [Path(s['path']).read_bytes() for s in chain['segments']]
        assert all(len(b) == s['file_bytes'] and sha(b) == s['stream_sha256']
                   for b, s in zip(blobs, chain['segments']))
        expected = b''.join(pwm_duties(compact.decode_model(b)).tobytes() for b in blobs)
        assert len(expected) == chain['samples']
        for irq in (0, 100):
            result = by_key[chain_id, irq]
            cost, report = result['cost'], result['report']
            folder = player / 'images' / chain_id / f'irq-{irq}'
            assert json.loads((folder / 'verification.json').read_text()) == result
            assert json.loads((folder / 'observer.json').read_text()) == report
            assert result['report_sha256'] == sha((folder / 'observer.json').read_bytes())
            actual = (folder / 'valid.pcm8').read_bytes()
            assert sha(actual) == result['pwm_sha256'] and validate(report, actual, expected)
            for name, field in (('player.elf', 'image_sha256'), ('program.bin', 'binary_sha256'), ('player.hex', 'hex_sha256')):
                assert sha((folder / name).read_bytes()) == cost[field]
            binary = (folder / 'program.bin').read_bytes()
            assert len(binary) == cost['flash_bytes'] == cost['text_bytes'] + cost['data_bytes']
            assert cost['program_flash_bytes'] == cost['flash_bytes'] - sum(map(len, blobs))
            assert cost['static_sram_bytes'] == cost['data_bytes'] + cost['bss_bytes']
            assert all(binary[start:end] == blob for (start, end), blob in zip(cost['embedded_segment_ranges'], blobs))
            assert result['passed'] and cost['embedded_streams_exact'] and cost['complete_image']
            assert cost['image_role'] == 'production-player' and cost['environment'] == environment
            assert result['validation_provenance'] == provenance
            rows.append({'chain_id': chain_id, 'profile': chain['profile'], 'irq': irq,
                         'roles': chain['roles'], 'cost': {k: cost[k] for k in numeric_cost},
                         'assembly_enabled': cost['assembly_enabled'], 'report': report,
                         'full_pwm_exact': True})
    paired = []
    for pair in binding['pairs']:
        for irq in (0, 100):
            old = by_key[pair['control'], irq]['cost']
            new = by_key[pair['selected'], irq]['cost']
            paired.append({k: pair[k] for k in ('mode', 'id', 'percent', 'profile', 'samples')}
                          | {'irq': irq, 'old_stream_bytes': old['stream_bytes'],
                             'new_stream_bytes': new['stream_bytes'],
                             'stream_bytes_delta': new['stream_bytes'] - old['stream_bytes'],
                             'old_full_flash_bytes': old['flash_bytes'],
                             'new_full_flash_bytes': new['flash_bytes'],
                             'full_flash_bytes_delta': new['flash_bytes'] - old['flash_bytes'],
                             'program_flash_bytes_delta': new['program_flash_bytes'] - old['program_flash_bytes'],
                             'static_sram_bytes_delta': new['static_sram_bytes'] - old['static_sram_bytes'],
                             'exact_active_irq_admission': True})
    summary = {'schema': 'lpx-v5-combined-player-anonymous-v1', 'status': 'passed',
               'base_source_commit': '0415d79149d3410d3afc74ba822160811e735184',
               'decoder_source_commit': '5c7e0592', 'source_sha256': source,
               'reproduction_driver_source_sha256': sha(driver.read_bytes()),
               'initial_measurement_driver_source_sha256': original_runs[0]['script_sha256'],
               'exporter_source_sha256': sha(Path(__file__).read_bytes()),
               'observer_runner_sha256': workers[0]['runner_sha256'],
               'runtime': {'wsl': provenance['runtime']['wsl'],
                           'sim_runner_sha256': provenance['runtime']['sim_runner_sha256'],
                           'libraries': {name: value['sha256'] for name, value in provenance['runtime']['libraries'].items()},
                           'resolved_libraries': provenance['runtime']['resolved_libraries'],
                           'python': provenance['python'], 'packages': provenance['packages']},
               'validation_source_sha256': provenance['sources'],
               'observer_runner_source_sha256': provenance['runner_sources'],
               'avr_build_environment': environment,
               'compiler_options_irq0': raw_rows[0]['result']['cost']['compiler_options'],
               'scope': {'profile_group_pairs': len({(p['id'], p['percent']) for p in binding['pairs']}),
                         'mode_role_pairs': len(binding['pairs']),
                         'unique_chains': len(chains), 'complete_images': len(rows),
                         'subset': 'all strict stream-byte savings versus an accepted control, plus the sole accepted 95% point',
                         'full_duration_samples_per_chain_min': min(c['samples'] for c in chains.values()),
                         'full_duration_samples_per_chain_max': max(c['samples'] for c in chains.values()),
                         'unique_chain_samples': sum(c['samples'] for c in chains.values()),
                         'observed_sample_ticks_across_images': sum(r['report']['timer_ticks'] for r in rows),
                         'physical_board': False, 'analog_output': False,
                         'all_other_combined_candidates_have_only_native_admission': True,
                         'cached_revalidation_performed': cached_revalidation,
                         'cache_revalidation_scope': 'When present, public-driver cache revalidation rechecks the same exact source/toolchain/output-bound images; it does not add independent runs.'},
               'normal_irq_flash_delta_counts': {
                   mode: dict(Counter(str(p['full_flash_bytes_delta']) for p in paired
                                      if p['mode'] == mode and p['irq'] == 0 and p['percent'] == 100))
                   for mode in ('sse', 'perceptual')},
               'minimum_stack_margin_all_bytes': min(r['report']['stack_margin_all_bytes'] for r in rows),
               'minimum_stack_margin_playback_bytes': min(r['report']['stack_margin_playback_bytes'] for r in rows),
               'maximum_irq_cycles': max(r['report']['irq_cycles_max'] for r in rows),
               'all_full_duration_pwm_eof_ticks_exact': True, 'underruns': 0,
               'decoder_errors': 0, 'observer_errors': 0, 'paired': paired, 'rows': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(summary, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps({'status': 'passed', 'images': len(rows),
                      'normal_irq_flash_delta_counts': summary['normal_irq_flash_delta_counts'],
                      'minimum_stack_margin_all_bytes': summary['minimum_stack_margin_all_bytes']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    main(args.study, args.output)
