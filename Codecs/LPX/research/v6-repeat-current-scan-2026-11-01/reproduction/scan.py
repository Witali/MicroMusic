"""Fixed 104-chain serialized-bit survey; no waveform/native/target operations."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import io
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tarfile
import time
import traceback

from serialized import (ROOT, ACTIVE, TOOLS, PROTOTYPE, compact, costs, histograms,
                        converter, reference, ForbiddenOperations, inspect,
                        empty_histogram, add_histogram, sha)

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent


def save(path, value):
    path = Path(path)
    if not path.resolve().is_relative_to(ROOT / 'build'):
        raise ValueError('Private output must remain in ignored build storage')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


class Inputs:
    def __init__(self): self.pins = {}
    def read(self, path, digest=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = sha(raw)
        if digest is not None and actual != digest or str(path) in self.pins and self.pins[str(path)] != actual:
            raise ValueError('An immutable serialized input changed')
        self.pins[str(path)] = actual
        return raw
    def json(self, path, digest=None): return json.loads(self.read(path, digest))
    def verify(self):
        if any(sha(Path(path).read_bytes()) != digest for path, digest in self.pins.items()):
            raise ValueError('A serialized input/source changed during the pass')


def sources():
    files = [*(ACTIVE / 'src').rglob('*'), *TOOLS.glob('*.py'), *HERE.glob('*.py'), PACKAGE / 'PROTOCOL.md',
             PROTOTYPE / 'scale_repeat.py', PROTOTYPE / 'reference.py']
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(set(files)) if p.is_file()}


def bind_source(commit, inputs):
    inventory = sources()
    targets = ['Codecs/LPX/01_ACTIVE_Q0_CODEC/src', 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools',
               HERE.relative_to(ROOT).as_posix(), (PACKAGE / 'PROTOCOL.md').relative_to(ROOT).as_posix(),
               PROTOTYPE.relative_to(ROOT).as_posix()]
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'archive', '--format=tar', commit, '--', *targets])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        expected = {member.name: sha(archive.extractfile(member).read()) for member in archive
                    if member.isfile() and member.name in inventory}
    if expected != inventory:
        raise ValueError('Executing sources differ from the explicit frozen commit')
    for name, digest in inventory.items(): inputs.read(ROOT / name, digest)
    old = inputs.json(PACKAGE.parent / 'v5-parameter-costs-2026-10-28/source-runtime.json')
    for name in ('speech_parameter_costs.py', 'speech_parameter_histograms.py'):
        key = '01_ACTIVE_Q0_CODEC/tools/' + name
        inputs.read(TOOLS / name, old['host_sources'][key])
    pilot = inputs.json(PACKAGE.parent / 'v6-scale-repeat-2026-10-28/pilot-source-runtime.json')
    for name in ('scale_repeat.py', 'reference.py'):
        matches = [digest for key, digest in pilot['host_sources'].items() if key.endswith('prototype/' + name)]
        if len(matches) != 1: raise ValueError('The audited raw adapter binding is ambiguous')
        inputs.read(PROTOTYPE / name, matches[0])
    for value, wanted in ((compact, TOOLS / 'speech_compact.py'), (costs, TOOLS / 'speech_parameter_costs.py'),
                          (histograms, TOOLS / 'speech_parameter_histograms.py'),
                          (converter, PROTOTYPE / 'scale_repeat.py'), (reference, PROTOTYPE / 'reference.py')):
        if Path(value.__file__).resolve() != wanted.resolve():
            raise ValueError('An operator was imported from another source epoch')
    return inventory


def load_baselines(path, inputs):
    marker = inputs.json(path.parent / 'complete-private.json')
    binding = inputs.json(path, marker['binding_sha256'])
    if (marker['status'] != 'complete' or not marker['all_input_and_source_guards_passed']
            or binding['schema'] != 'lpx-joint-rate-baselines-private-v1'
            or binding['status'] != 'prepared-no-search' or len(binding['baselines']) != 104):
        raise ValueError('Require the original frozen current-104 baseline binding')
    rows = binding['baselines']
    if len({row['id'] for row in rows}) != 104 or Counter(row['profile'] for row in rows) != {4: 52, 6: 52}:
        raise ValueError('The fixed baseline population/profile allocation changed')
    return rows


def freeze_histograms(value):
    if isinstance(value, Counter): return {str(k): value[k] for k in sorted(value)}
    if isinstance(value, dict): return {k: freeze_histograms(v) for k, v in value.items()}
    return value


def summarize(rows):
    saved = [r['stored_bytes_saved'] for r in rows]
    return dict(chains=len(rows), current_stored_bytes=sum(r['current_stored_bytes'] for r in rows),
        hypothetical_v6_stored_bytes=sum(r['hypothetical_v6_stored_bytes'] for r in rows),
        stored_bytes_saved=sum(saved), saved_bytes_min_median_max=[min(saved), statistics.median(saved), max(saved)],
        positive_zero_negative=[sum(v > 0 for v in saved), sum(v == 0 for v in saved), sum(v < 0 for v in saved)],
        all_hypothetical_segments_within_uint16=all(r['all_hypothetical_segments_within_uint16'] for r in rows))


def analyze(baselines, inputs, progress=None):
    chains, segments, private, cache = [], [], [], {}
    grouped_hist = defaultdict(empty_histogram)
    census = Counter()
    for ordinal, base in enumerate(baselines, 1):
        identifier = 'chain-%03d' % ordinal
        storage = 'SPI-required-data-alone' if base['stream_bytes'] > 32768 else 'ROM-data-eligible'
        domain = 'nonspeech' if base['nonspeech'] else 'speech'
        group = (domain, base['profile'], storage)
        position = total = proposed = 0
        proofs = []
        for index, part in enumerate(base['segments']):
            blob = inputs.read(part['path'], part['stream_sha256'])
            if (part['index'] != index or part['start'] != position or part['profile'] != base['profile']
                    or len(blob) != part['file_bytes'] or not 22 <= len(blob) <= 65535):
                raise ValueError('Actual ordered baseline geometry/size changed')
            digest = sha(blob)
            if digest not in cache:
                cache[digest] = inspect(blob)
            info, cost, verification = cache[digest]
            if info['profile'] != base['profile'] or info['samples'] != part['samples']:
                raise ValueError('Serialized profile/sample count differs from the bound metadata')
            position += info['samples']; total += len(blob); proposed += cost['proposed_file_bytes']
            add_histogram(grouped_hist[group], info)
            coded = histograms.parameter_codes(info['params'])
            census['stored_tuples'] += info['stored_tuples']
            census['audible_tuples'] += info['audible_tuples']
            census['unplayed_stored_tuples'] += info['unplayed_stored_tuples']
            census['gain_zero_stored_tuples'] += sum(gain == 0 for scale, lag, gain in coded)
            census['gain_zero_lag_changes'] += sum(b[2] == 0 and b[1] != a[1] for a, b in zip(coded, coded[1:]))
            census['raw_scale_codes_0_to_5'] += sum(scale <= 5 for scale, lag, gain in coded)
            census['raw_scale_codes_6_to_9'] += sum(6 <= scale <= 9 for scale, lag, gain in coded)
            row = dict(chain=identifier, segment=index, domain=domain, profile=base['profile'], storage_class=storage,
                samples=info['samples'], current_stored_bytes=len(blob), hypothetical_v6_stored_bytes=cost['proposed_file_bytes'],
                stored_bytes_saved=cost['whole_stream_saved_bytes'],
                **{key: cost[key] for key in ('current_payload_bits', 'current_parameter_bits', 'current_padding_bits',
                    'proposed_parameter_bits', 'proposed_payload_bits', 'proposed_padding_bits',
                    'additional_selector_bytes', 'source_extras_flag', 'source_extra_marker_bits', 'source_extra_value_bits')},
                stored_tuples=info['stored_tuples'], unplayed_stored_tuples=info['unplayed_stored_tuples'],
                current_uint16_bound=len(blob) <= 65535, hypothetical_uint16_bound=cost['same_rom_api_size_fits'],
                byte_roundtrip_verified=True, independent_parameter_roundtrip_verified=True,
                noncanonical_source_preserved=verification['noncanonical_source_retained_without_normalizing'])
            segments.append(row)
            proofs.append(dict(segment=part, source_sha256=digest, verification=verification))
        if position != base['samples'] or total != base['stream_bytes']:
            raise ValueError('The full chain was shortened or its stored byte cost changed')
        n = len(base['segments'])
        row = dict(chain=identifier, domain=domain, profile=base['profile'], level_mode=base['mode'],
            samples=position, reset_segments=n, storage_class=storage, current_stored_bytes=total,
            hypothetical_v6_stored_bytes=proposed, stored_bytes_saved=total - proposed,
            original_data_alone_within_32768=total <= 32768, hypothetical_data_alone_within_32768=proposed <= 32768,
            all_hypothetical_segments_within_uint16=all(r['hypothetical_uint16_bound'] for r in segments[-n:]),
            rom_embedded_audio_bytes_if_chosen=dict(current=total, hypothetical=proposed),
            spi_mcu_embedded_audio_bytes=dict(current=0, hypothetical=0),
            unlinked_avr_table_span_bytes=dict(ROM=4 * n, SPI=6 * n),
            linked_program_flash_bytes=None, linked_metadata_flash_bytes=None, net_complete_flash_saved_bytes=None,
            static_sram_bytes=None, stack_margin_bytes=None, native_pcm_pwm_verified=False, IRQ_verified=False)
        chains.append(row)
        private.append(dict(chain=identifier, baseline_id=base['id'], source_choice=base['source_choice'],
            reference=base['reference'], level=base['level'], target_reference_pcm16_sha256=base['target_reference_pcm16_sha256'],
            source_proofs=proofs))
        if progress: progress(ordinal)
    groups = []
    for key in sorted(grouped_hist):
        selected = [r for r in chains if (r['domain'], r['profile'], r['storage_class']) == key]
        groups.append(dict(domain=key[0], profile=key[1], storage_class=key[2], **summarize(selected)))
    summary = dict(schema='lpx-current-repeat-serialized-cost-v1', status='complete', chains=104,
        reset_segment_occurrences=len(segments), unique_stored_streams=len(cache), method=asdict(costs.METHODS[0]),
        overall=summarize(chains), groups=groups, census=dict(census),
        complete_byte_roundtrip_unique_streams=len(cache), independent_raw_roundtrip_unique_streams=len(cache),
        canonical_v5_writer_unique_streams=sum(v[2]['existing_v5_writer_byte_exact'] for v in cache.values()),
        noncanonical_unique_streams_preserved=sum(v[2]['noncanonical_source_retained_without_normalizing'] for v in cache.values()),
        waveform_synthesis_calls=0, quality_metric_calls=0, fitting_calls=0, native_builds=0, target_jobs=0, simulations=0,
        complete_flash_measured=False, native_pcm_pwm_verified=False, physical_board_claim=False,
        scope='Complete serialized bytes only; program, linked metadata, SRAM/stack and IRQ admission remain unmeasured')
    hist = [dict(domain=k[0], profile=k[1], storage_class=k[2], histogram=freeze_histograms(v))
            for k, v in sorted(grouped_hist.items())]
    return dict(summary=summary, chains=chains, segments=segments, histograms=hist), private


def run(args):
    if args.output.exists() or not args.output.is_relative_to(ROOT / 'build'):
        raise ValueError('Use a fresh distinct ignored output folder')
    args.output.mkdir(parents=True)
    started = time.perf_counter(), time.process_time()
    events = []
    save(args.output / 'attempt-started-private.json', dict(status='started', expected_chains=104,
        new_waveform_or_native_or_target_operations=0))
    try:
        inputs = Inputs()
        inventory = bind_source(args.source_commit, inputs)
        baselines = load_baselines(args.baselines, inputs)
        save(args.output / 'binding-private.json', dict(schema='lpx-current-repeat-binding-private-v1',
            source_commit=args.source_commit, source_inventory=inventory, baselines_path=str(args.baselines),
            baseline_binding_sha256=sha(args.baselines.read_bytes()), method=asdict(costs.METHODS[0]),
            expected_chains=104, expected_segments=sum(len(b['segments']) for b in baselines),
            initial_input_files_sha256=inputs.pins.copy()))
        def progress(ordinal):
            events.append(dict(ordinal=ordinal, status='complete'))
            if ordinal % 20 == 0 or ordinal == 104:
                print(json.dumps(dict(completed_chains=ordinal, expected_chains=104)), flush=True)
        with ForbiddenOperations() as guard:
            public, private = analyze(baselines, inputs, progress)
            inputs.verify()
            if sources() != inventory or guard.attempts:
                raise ValueError('Sources changed or a forbidden operation was attempted')
            save(args.output / 'results-private.json', dict(status='complete', public=public, rows=private,
                input_files_sha256=inputs.pins, forbidden_operation_attempts=guard.attempts))
            save(args.output / 'attempt-terminal-private.json', dict(status='complete', events=events,
                elapsed=dict(wall_seconds=time.perf_counter() - started[0], cpu_seconds=time.process_time() - started[1]),
                forbidden_operation_attempts=guard.attempts))
            save(args.output / 'complete-private.json', dict(status='complete',
                results_sha256=sha((args.output / 'results-private.json').read_bytes()),
                binding_sha256=sha((args.output / 'binding-private.json').read_bytes()),
                terminal_sha256=sha((args.output / 'attempt-terminal-private.json').read_bytes())))
        print(json.dumps(public['summary']), flush=True)
    except Exception as exc:
        save(args.output / 'failure-private.json', dict(status='failed', exception_type=type(exc).__name__,
            events=events, traceback=traceback.format_exc()))
        raise


def reopen(study):
    inputs = Inputs()
    marker = inputs.json(study / 'complete-private.json')
    binding = inputs.json(study / 'binding-private.json', marker['binding_sha256'])
    result = inputs.json(study / 'results-private.json', marker['results_sha256'])
    attempt = inputs.json(study / 'attempt-terminal-private.json', marker['terminal_sha256'])
    if (marker['status'] != result['status'] or result['status'] != attempt['status'] or attempt['status'] != 'complete'
            or attempt['events'] != [dict(ordinal=i, status='complete') for i in range(1, 105)]
            or result['forbidden_operation_attempts'] or attempt['forbidden_operation_attempts']):
        raise ValueError('The fixed serialized study is not terminal')
    if sources() != binding['source_inventory']:
        raise ValueError('Measured serialized sources changed')
    for path, digest in result['input_files_sha256'].items(): inputs.read(path, digest)
    return inputs, binding, result


def audit(args):
    inputs, binding, saved = reopen(args.study)
    baselines = load_baselines(Path(binding['baselines_path']), inputs)
    with ForbiddenOperations() as guard:
        public, private = analyze(baselines, inputs)
        if public != saved['public'] or private != saved['rows'] or guard.attempts:
            raise AssertionError('Serialized audit/reconstruction differs')
        inputs.verify()
    save(args.study / 'audit-private.json', dict(status='passed', source_inventory=binding['source_inventory'],
        results_sha256=sha((args.study / 'results-private.json').read_bytes()), chains=104,
        reset_segment_occurrences=public['summary']['reset_segment_occurrences'],
        unique_stored_streams=public['summary']['unique_stored_streams'],
        scope='Read-only serialized replay; no synthesis/metrics/native/target operations', forbidden_operation_attempts=[]))
    print(json.dumps(dict(status='passed serialized replay', chains=104)), flush=True)


def publish(args):
    inputs, binding, saved = reopen(args.study)
    receipt = inputs.json(args.study / 'audit-private.json')
    if receipt['status'] != 'passed' or receipt['results_sha256'] != sha((args.study / 'results-private.json').read_bytes()):
        raise ValueError('Require the completed serialized replay')
    for name, value in saved['public'].items():
        path = PACKAGE / (name + '.json')
        raw = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('Preserve a different public projection')
        path.write_bytes(raw)
    source = dict(schema='lpx-current-repeat-software-sources-v1', source_commit=binding['source_commit'],
        software_sources_sha256=binding['source_inventory'], method=asdict(costs.METHODS[0]),
        private_input_or_stream_fingerprints_exported=False)
    path = HERE / 'sources.json'
    raw = (json.dumps(source, indent=2, allow_nan=False) + '\n').encode()
    if path.exists() and path.read_bytes() != raw: raise ValueError('Preserve a different source projection')
    path.write_bytes(raw)
    print('{"status":"anonymous serialized costs published locally","target_jobs":0}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'audit', 'publish'))
    parser.add_argument('--baselines', type=Path)
    parser.add_argument('--source-commit')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--study', type=Path)
    args = parser.parse_args()
    for name in ('baselines', 'output', 'study'):
        value = getattr(args, name)
        if value is not None: setattr(args, name, value.resolve())
    if args.action == 'run':
        if not all((args.baselines, args.source_commit, args.output)): parser.error('Run requires baselines/source-commit/output')
        run(args)
    else:
        if args.study is None: parser.error('Audit/publish requires study')
        (audit if args.action == 'audit' else publish)(args)


if __name__ == '__main__': main()
