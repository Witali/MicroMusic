"""Independently recheck complete linked images and full retained PWM evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path.cwd()
HERE = ROOT / 'Codecs/LPX/research/v6-scale-repeat-2026-10-28/prototype'
sys.path[:0] = [str(HERE), str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'), str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tests')]
import numpy as np
from benchmark_speech_flash import canonical, source_hashes, environment, runtime_fingerprint
from build_release_player import EXAMPLE
from pilot import prepare, sources, save
from scale_repeat import from_v5
from reference import restore_v5, decode_model
from standard_metrics import pwm_duties

sha = lambda data: hashlib.sha256(data).hexdigest()
load = lambda path: json.loads(path.read_text())


def main(args):
    started = time.perf_counter()
    folder = args.study
    assert folder.resolve().is_relative_to((ROOT / 'build').resolve())
    private = load(folder / 'results-private.json')
    public = load(folder / 'rows.json')
    summary = load(folder / 'summary.json')
    binding = load(folder / 'source-runtime.json')
    if any(item['status'] != 'complete' for item in (private, public, summary)):
        raise ValueError('Expected complete pilot')
    if sources() != binding['host_sources']:
        raise ValueError('Pilot host source changed')
    actual_runtime = runtime_fingerprint(folder / 'observer/sim_player', args.lib, args.wsl)
    assert actual_runtime == binding['validation']['runtime']
    production = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'
    derived = folder / 'derived/src'
    if source_hashes(production) != binding['source']['production_source_sha256'] or source_hashes(derived) != binding['source']['derived_source_sha256']:
        raise ValueError('Pilot decoder sources changed')
    cases, manifest_digest = prepare(args.manifest)
    if manifest_digest != private['manifest_sha256']:
        raise ValueError('Pilot manifest changed')
    cases = {case['id']: case for case in cases}
    expected = {}
    original = {}
    converted = {}
    for identity, case in cases.items():
        original[identity] = case['streams']
        converted[identity] = [from_v5(blob) for blob in original[identity]]
        pcm = []
        for before, after in zip(original[identity], converted[identity]):
            if restore_v5(after)[0] != before:
                raise AssertionError('Independent raw bit reconstruction changed')
            pcm.append(decode_model(after))
        expected[identity] = pwm_duties(np.concatenate(pcm)).tobytes()
        if 'baseline_pwm_sha256' in case and (sha(expected[identity]) != case['baseline_pwm_sha256'] or sha(np.concatenate(pcm).astype('<i2').tobytes()) != case['baseline_pcm16_sha256']):
            raise AssertionError('Frozen full original output changed')
    assert len(public['rows']) == len(private['rows']) == 34
    rows = {tuple(r[k] for k in ('id', 'role', 'backend', 'extra_irq_cycles')): r for r in public['rows']}
    assert len(rows) == 34
    chain_samples = image_checks = embedded_checks = valid_pwm_samples = 0
    asm_good = c_failed = 0
    dependencies = None
    for row in private['rows']:
        key = tuple(row[k] for k in ('id', 'role', 'backend', 'extra_irq_cycles'))
        projection = rows[key]
        assert all(projection[k] == row[k] for k in projection)
        result = row['verification']
        assert result['validation_provenance']['runtime'] == actual_runtime
        cost = result['cost']
        directory = Path(row['output'])
        assert directory.is_relative_to(folder.resolve())
        streams = original[row['id']] if row['role'] == 'v5-control' else converted[row['id']]
        assert [sha(blob) for blob in streams] == cost['stream_sha256'] == row['streams_sha256']
        assert len(streams) == cost['segments'] == row['segments']
        assert sum(map(len, streams)) == cost['stream_bytes'] == row['stream_bytes']
        assert cost['complete_image'] and cost['embedded_streams_exact'] and cost['measurement'] == 'linked-elf-text-plus-data'
        assert cost['source_fingerprint'] == sha(canonical(source_hashes(production if row['role'] == 'v5-control' else derived)))
        assert cost['assembly_enabled'] == (row['backend'] == 'explicit-avr-asm')
        assert cost['queue'] == 256 and cost['prefill'] == 192
        if dependencies is None:
            env = environment(production, args.avr_bin, True, harness=EXAMPLE / 'player.cpp', required_symbols=(), retained_symbols=())
            dependencies = env['dependencies']
        assert cost['environment']['dependencies'] == dependencies
        for name, field in (('player.elf', 'image_sha256'), ('program.bin', 'binary_sha256'), ('player.hex', 'hex_sha256')):
            assert sha((directory / name).read_bytes()) == cost[field]
        size = subprocess.check_output([str(args.avr_bin / 'avr-size.exe'), str(directory / 'player.elf')], text=True)
        text, data, bss = map(int, re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+', size, re.M).groups())
        assert (text, data, bss) == (cost['text_bytes'], cost['data_bytes'], cost['bss_bytes'])
        assert text + data == cost['flash_bytes'] == row['flash_bytes'] <= 32768
        assert text + data - sum(map(len, streams)) == cost['program_flash_bytes'] == row['program_flash_bytes']
        assert data + bss == cost['static_sram_bytes'] == row['static_sram_bytes'] == 756
        binary = (directory / 'program.bin').read_bytes()
        with tempfile.TemporaryDirectory(dir=folder) as temporary:
            recovered = Path(temporary) / 'recovered.bin'
            subprocess.run([str(args.avr_bin / 'avr-objcopy.exe'), '-O', 'binary', '-R', '.eeprom', str(directory / 'player.elf'), str(recovered)], check=True, capture_output=True)
            assert recovered.read_bytes() == binary
        symbols = subprocess.check_output([str(args.avr_bin / 'avr-nm.exe'), '-S', '--defined-only', str(directory / 'player.elf')], text=True)
        assert 'profile_' not in symbols and 'lpx_player_hardware' not in symbols
        regions = []
        for index, blob in enumerate(streams):
            matches = []
            for line in symbols.splitlines():
                parts = line.split()
                if len(parts) >= 4 and re.fullmatch(r'.*lpx_voice_' + str(index) + r'(?:\..*)?', parts[-1]) and int(parts[1], 16) == len(blob):
                    address = int(parts[0], 16)
                    if binary[address:address + len(blob)] == blob:
                        matches.append(address)
            assert len(matches) == 1
            start = matches[0]
            assert all(not (start < end and begin < start + len(blob)) for begin, end in regions)
            regions.append((start, start + len(blob)))
            embedded_checks += 1
        report = load(directory / 'observer.json')
        actual = (directory / 'valid.pcm8').read_bytes()
        assert report == row['report'] == result['report']
        assert sha((directory / 'observer.json').read_bytes()) == result['report_sha256']
        assert sha(actual) == result['pwm_sha256']
        assert actual == expected[row['id']] and len(actual) == row['samples']
        assert report['stopped'] == report['eof'] == report['timer_started'] == 1
        assert report['decoder_error'] == report['observer_errors'] == report['observer_exit_code'] == report['queued_at_stop'] == 0
        assert report['produced'] == report['played'] == row['samples']
        assert report['timer_ticks'] == report['timer_events'] == row['samples'] + report['underruns']
        assert report['stack_margin_all_bytes'] > 0
        assert row['adapter_sources_sha256'] == {name: value for name, value in binding['host_sources'].items() if name.endswith(('scale_repeat.py', 'reference.py'))}
        # Explicit model adapter source, actual image and expectation all bind the outer protocol.
        expected_fingerprint = sha(canonical([result['validation_provenance'], cost['image_sha256'], sha((directory / 'observer.txt').read_bytes()), sha(expected[row['id']]), 0]))
        assert result['fingerprint'] == expected_fingerprint
        if row['backend'] == 'explicit-avr-asm':
            assert report['underruns'] == 0 and row['timing_admitted'] and result['passed']
            asm_good += 1
        else:
            assert report['underruns'] > 0 and not row['timing_admitted'] and not result['passed']
            c_failed += 1
        valid_pwm_samples += len(actual)
        image_checks += 1
    assert asm_good == 32 and c_failed == 2
    assert summary['actual_complete_linked_images'] == 34 and summary['asm_timing_admitted'] == 32
    receipt = {'schema': 'lpx-scale-repeat-independent-player-audit-v1', 'status': 'passed',
               'actual_complete_linked_images_checked': image_checks, 'exact_embedded_segment_regions': embedded_checks,
               'complete_valid_pwm_samples_checked_including_c_observations': valid_pwm_samples,
               'asm_full_pwm_eof_tick_queue_stack_and_zero_underrun_passes': asm_good,
               'c_exact_valid_sample_sequence_but_timing_failures_retained': c_failed,
               'static_sram_bytes_all_images': 756, 'source_toolchain_image_stream_and_adapter_bindings_checked': True,
               'private_media_fingerprints_exported': False, 'production_source_unchanged': True,
               'audit_source_sha256': sha(Path(__file__).read_bytes()), 'seconds': time.perf_counter() - started,
               'scope': 'ASM images compare every physical output tick. C valid-sample output is exact but underruns add idle ticks, so physical C output is not equivalent in real time. No board or audibility claim.'}
    save(args.output, receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--avr-bin', type=Path, required=True)
    parser.add_argument('--lib', type=Path, required=True)
    parser.add_argument('--wsl')
    main(parser.parse_args())
