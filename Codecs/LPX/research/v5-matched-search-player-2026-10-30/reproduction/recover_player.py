"""Explicit recovery of one pre-image Windows journal-replace failure.

The original dispatcher and failed worker stay immutable. Its completed prefix
is strictly reopened, never simulated again. Only its original pending suffix
can build images. This module changes atomic-save robustness, not target proof.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import traceback
from types import SimpleNamespace

THIS = Path(__file__).resolve()
GENERIC = THIS.parents[2]/'v5-adaptive-player-union-2026-10-30/reproduction'
sys.path.insert(0, str(GENERIC))
import measure_union as base

REPLACE_DELAYS = (.01, .02, .04, .08, .16)


def require(value, message):
    if not value:
        raise ValueError(message)


def replace_with_retry(temporary, target, on_retry=None):
    """At most six replace attempts; retry only Windows sharing/access errors.

    The caller writes the temporary once. Exhaustion leaves that exact file
    intact. Non-Windows or other errors propagate immediately.
    """
    for attempt in range(len(REPLACE_DELAYS)+1):
        try:
            temporary.replace(target)
            return
        except OSError as error:
            if getattr(error, 'winerror', None) not in (5, 32) or attempt == len(REPLACE_DELAYS):
                raise
            if on_retry is not None:
                on_retry(getattr(error, 'winerror'), attempt+1)
            time.sleep(REPLACE_DELAYS[attempt])


def write_once(path, value):
    require(not path.exists(), 'Preserve the existing recovery receipt')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.writing')
    require(not temporary.exists(), 'Preserve the existing incomplete recovery receipt')
    temporary.write_bytes(json.dumps(value, indent=2, allow_nan=False).encode()+b'\n')
    replace_with_retry(temporary, path)


def expected_keys(handoff, shard):
    return [(item['id'], irq) for index, item in enumerate(handoff['chains'])
            if index % 2 == shard for irq in (0, 100)]


def prefix_keys(rows, expected):
    keys = [(row['chain'], row['extra_irq_cycles']) for row in rows]
    require(keys == expected[:len(rows)] and len(rows) < len(expected),
            'Completed proofs are not one exact proper prefix')
    require(all(row['passed'] and row['verification'] is not None for row in rows),
            'This bounded recovery requires the observed positive prefix')
    return expected[len(rows):]


def original_state(args):
    raw = args.handoff.read_bytes()
    handoff = json.loads(raw)
    folder = args.campaign/'workers/shard-0'
    names = ('attempt-private.json', 'failure-private.json', 'rows.json', 'results-private.json')
    files = {str(folder/name): base.sha((folder/name).read_bytes()) for name in names}
    for path in folder.glob('*.writing'):
        files[str(path)] = base.sha(path.read_bytes())
    attempt, failure, visible, result = [base.load(folder/name) for name in names]
    require(attempt['status'] == 'failed' and attempt['exception_type'] == 'PermissionError'
            and failure['exception_type'] == 'PermissionError' and '[WinError 5]' in failure['traceback'],
            'The original observed host-filesystem failure differs')
    require(result['status'] == visible['status'] == 'running' and result['shard'] == 0
            and result['handoff_sha256'] == attempt['handoff_sha256'] == base.sha(raw),
            'Original worker/handoff receipt differs')
    rows = result['rows']
    require(len(rows) == 91 and len(visible['rows']) == 91, 'Original 91-row prefix differs')
    for hidden, public in zip(rows, visible['rows']):
        require(all(hidden[name] == value for name, value in public.items()), 'Original public/private row differs')
    expected = expected_keys(handoff, 0)
    remaining = prefix_keys(rows, expected)
    require(len(expected) == 188 and len(remaining) == 97, 'Original shard-0 finite scope differs')
    events = attempt['events']
    require(len(events) == 92 and all(event['status'] == 'passed' for event in events[:-1]),
            'Original completed attempt events differ')
    require([(event['chain'], event['extra_irq_cycles']) for event in events[:-1]] == expected[:91],
            'Original event prefix differs')
    pending = events[-1]
    require(pending['status'] == 'running' and (pending['chain'], pending['extra_irq_cycles']) == remaining[0],
            'The original interrupted event differs')
    # The source location is before image selection/build; absence is mandatory.
    dispatcher = (GENERIC/'measure_union.py').read_text().splitlines()
    require("attempt['events'].append(event); epoch.save(attempt_path,attempt)" in dispatcher[125],
            'Original failure source point changed')
    image = args.campaign/'images'/pending['chain']/('irq-%d' % pending['extra_irq_cycles'])
    require(not image.exists(), 'The pending event has an image; do not call it unstarted')
    items = {item['id']: item for item in handoff['chains']}
    for row in rows:
        entry = items[row['chain']]['entry']
        require(row['stream_sha256'] == [part['stream_sha256'] for part in entry['segments']],
                'Original completed stream tuple differs')
    return raw, handoff, rows, files, remaining


def guard_recovery(binding):
    require(base.sha(THIS.read_bytes()) == binding['recovery_source_sha256'], 'Recovery source changed')
    for name, digest in binding['original_files_sha256'].items():
        require(base.sha(Path(name).read_bytes()) == digest, 'An original failed-worker artifact changed')


def run(args):
    require(not args.recovery.exists(), 'Use fresh explicitly audited recovery state')
    require(args.recovery.is_relative_to(args.campaign/'recoveries'), 'Recovery state must stay inside the campaign')
    raw, handoff, original, files, remaining = original_state(args)
    binding = dict(schema='lpx-matched-search-rom-recovery-binding-private-v1',
        original_handoff_sha256=base.sha(raw), recovery_source_sha256=base.sha(THIS.read_bytes()),
        original_files_sha256=files, original_prefix_rows=91, original_pending_rows=97,
        original_failed_shard=0, original_pending_key=list(remaining[0]),
        pending_original_image_absent=True, original_dispatcher_unchanged=True,
        replace_attempt_limit=6, replace_retry_winerrors=[5, 32], replace_delays_seconds=list(REPLACE_DELAYS),
        no_fits=True, no_endpoint_or_configuration_changes=True)
    write_once(args.recovery/'binding-private.json', binding)
    old_guard, old_index = base.guard, base.prior_index
    retries = []
    def guarded(epoch, current, current_raw, state, all_inputs=False):
        old_guard(epoch, current, current_raw, state, all_inputs)
        guard_recovery(binding)
    def prior_index(current):
        index = old_index(current)
        for row in original:
            index[(tuple(row['stream_sha256']), row['extra_irq_cycles'])] = row
        return index
    def save(epoch, path, value):
        path = epoch.output(path)
        temporary = path.with_suffix('.writing')
        epoch.output(temporary)
        require(not temporary.exists(), 'Preserve the incomplete atomic write before another save')
        epoch.modules['output_paths'].protect_outputs(
            [Path(base.__file__), *[epoch.root/name for name in epoch.snapshot()]], [path, temporary])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
        replace_with_retry(temporary, path,
            lambda error, attempt: retries.append(dict(winerror=error, replace_attempt=attempt)))
    base.guard = guarded
    base.prior_index = prior_index
    base.Epoch.save = save
    state = SimpleNamespace(source_root=args.source_root, handoff=args.handoff, output=args.recovery, shard=0)
    code = base.run(state)
    require(code == 0, 'The explicit recovery worker did not complete')
    result = base.load(args.recovery/'workers/shard-0/results-private.json')
    require(result['status'] == 'complete' and len(result['rows']) == 188, 'Recovery coverage differs')
    for old, reopened in zip(original, result['rows'][:91]):
        require(reopened['reused_frozen_image'] and not reopened['newly_built_and_simulated']
                and reopened['verification'] == old['verification'] and reopened['output'] == old['output'],
                'A completed original prefix proof was not strictly reopened')
    suffix = result['rows'][91:]
    require([(row['chain'], row['extra_irq_cycles']) for row in suffix] == remaining,
            'Recovery expanded or reordered the pending suffix')
    guard_recovery(binding)
    original_state(args)
    receipt = dict(schema='lpx-matched-search-rom-recovery-private-v1', status='complete',
        handoff_sha256=base.sha(raw), binding_sha256=base.sha((args.recovery/'binding-private.json').read_bytes()),
        recovery_source_sha256=binding['recovery_source_sha256'], original_completed_rows_reopened=91,
        original_pending_rows_completed=97, completed_prefix_simulations_repeated=0,
        new_images_in_pending=sum(row['newly_built_and_simulated'] for row in suffix),
        strict_prior_reuses_in_pending=sum(row['reused_frozen_image'] for row in suffix),
        no_fit_in_pending=sum(row['status'].startswith('no-fit') for row in suffix),
        recovery_worker_files_sha256={name: base.sha((args.recovery/'workers/shard-0'/name).read_bytes())
            for name in ('attempt-private.json', 'rows.json', 'results-private.json', 'summary.json')},
        atomic_replace_retry_events=retries, new_fits=0)
    write_once(args.recovery/'recovery-private.json', receipt)
    print(json.dumps({name: receipt[name] for name in ('status', 'original_completed_rows_reopened',
        'original_pending_rows_completed', 'completed_prefix_simulations_repeated',
        'new_images_in_pending', 'strict_prior_reuses_in_pending', 'no_fit_in_pending', 'new_fits')}), flush=True)
    return 0


def collected(args, handoff, raw):
    """Resolve the explicit recovery without rewriting the failed original row."""
    binding = base.load(args.recovery/'binding-private.json')
    receipt = base.load(args.recovery/'recovery-private.json')
    guard_recovery(binding)
    original_state(args)
    require(receipt['status'] == 'complete' and receipt['handoff_sha256'] == binding['original_handoff_sha256'] == base.sha(raw)
            and receipt['binding_sha256'] == base.sha((args.recovery/'binding-private.json').read_bytes())
            and receipt['recovery_source_sha256'] == binding['recovery_source_sha256'], 'Recovery receipt differs')
    for name, digest in receipt['recovery_worker_files_sha256'].items():
        require(base.sha((args.recovery/'workers/shard-0'/name).read_bytes()) == digest,
                'A completed recovery worker artifact changed')
    old = base.load(args.campaign/'workers/shard-0/results-private.json')
    failed = base.load(args.campaign/'workers/shard-0/attempt-private.json')
    recovered = base.load(args.recovery/'workers/shard-0/results-private.json')
    recovered_attempt = base.load(args.recovery/'workers/shard-0/attempt-private.json')
    other = base.load(args.campaign/'workers/shard-1/results-private.json')
    other_attempt = base.load(args.campaign/'workers/shard-1/attempt-private.json')
    require(failed['status'] == 'failed' and recovered_attempt['status'] == other_attempt['status'] == 'complete',
            'Original failure or terminal attempts differ')
    require(recovered['status'] == other['status'] == 'complete' and recovered['shard'] == 0 and other['shard'] == 1
            and recovered['handoff_sha256'] == other['handoff_sha256'] == base.sha(raw), 'Terminal handoff differs')
    require(len(old['rows']) == 91 and len(recovered['rows']) == 188 and len(other['rows']) == 186,
            'Terminal row counts differ')
    require([(r['chain'], r['extra_irq_cycles']) for r in recovered['rows']] == expected_keys(handoff, 0),
            'Recovery audit/suffix order differs')
    allowed = ('passed', 'no-fit-data-alone', 'no-fit-linked-flash', 'timing-or-output-failed')
    for result, attempt in ((recovered, recovered_attempt), (other, other_attempt)):
        require(len(result['rows']) == len(attempt['events']) and all(event['status'] in allowed
                and event['status'] == row['status'] and event['passed'] == row['passed']
                for event, row in zip(attempt['events'], result['rows'])), 'Terminal event/result mapping differs')
    require(all(row['reused_frozen_image'] and not row['newly_built_and_simulated']
                and row['verification'] == prior['verification']
                for prior, row in zip(old['rows'], recovered['rows'][:91])), 'Completed prefix was repeated')
    joined0 = [*old['rows'], *recovered['rows'][91:]]
    joined = [*joined0, *other['rows']]
    require([(r['chain'], r['extra_irq_cycles']) for r in joined0] == expected_keys(handoff, 0)
            and [(r['chain'], r['extra_irq_cycles']) for r in other['rows']] == expected_keys(handoff, 1),
            'Recovered logical row population differs')
    require(len({(r['chain'], r['extra_irq_cycles']) for r in joined}) == 374, 'Repeated logical image row')
    numeric = dict(worker_attempts=3, failed_worker_attempts=1, host_filesystem_failures_before_image=1,
        original_completed_proofs_reopened=91, original_pending_rows_completed=97,
        completed_simulations_repeated=0, atomic_replace_retry_events=len(receipt['atomic_replace_retry_events']))
    logical0 = dict(status='complete', shard=0, recovered=True, chains=94, rows=188,
        passed=sum(row['passed'] for row in joined0),
        newly_built_and_simulated=sum(row['newly_built_and_simulated'] for row in joined0),
        reused_frozen_images=sum(row['reused_frozen_image'] for row in joined0),
        no_fit=sum(row['status'].startswith('no-fit') for row in joined0),
        timing_or_output_failures=sum(row['status'] == 'timing-or-output-failed' for row in joined0),
        original_failed_attempt_completed_rows=91, recovery_audit_rows=188, recovery_new_scope_rows=97,
        combined_worker_wall_seconds=None, new_fits=0)
    return joined, [logical0, other['summary']], numeric


def aggregate(args):
    state = SimpleNamespace(source_root=args.source_root, handoff=args.handoff)
    epoch, proof, handoff, raw = base.context(state)
    joined, workers, recovery = collected(args, handoff, raw)
    output = epoch.output(args.campaign)
    for name in ('rows.json', 'results-private.json', 'summary.json', 'source-runtime.json'):
        require(not (output/name).exists(), 'Preserve any previous aggregate before an explicit audited recovery')
    indexed = {(row['chain'], row['extra_irq_cycles']): row for row in joined}
    public, private = [], []
    for item in handoff['chains']:
        streams = base.bound_streams(item, epoch)
        entry = item['entry']
        expected = None
        if entry['file_bytes'] <= base.FLASH_BYTES:
            import numpy as np
            pcm = np.concatenate([epoch.modules['speech_compact'].decode_model(blob) for blob in streams])
            expected = epoch.modules['standard_metrics'].pwm_duties(pcm).tobytes()
            require(base.sha(pcm.astype('<i2').tobytes()) == entry['pcm16_sha256'] and base.sha(expected) == entry['pwm_sha256'],
                    'Whole model output changed')
        for irq in (0, 100):
            row = indexed[item['id'], irq]
            require(row['stream_sha256'] == [base.sha(blob) for blob in streams]
                    and row['stream_bytes'] == sum(map(len, streams)), 'Stored image input differs')
            if row['verification'] is not None:
                if row['passed']:
                    proof.reuse(row, streams, expected, irq)
                else:
                    base.verify_failed_image(proof, row, streams, expected)
            elif row['status'] == 'no-fit-data-alone':
                require(entry['file_bytes'] > base.FLASH_BYTES, 'Data-only no-fit classification differs')
            else:
                require(row['status'] == 'no-fit-linked-flash', 'Unknown terminal image state')
                log = Path(row['output'])/'compile.stderr.log'
                require(base.sha(log.read_bytes()) == row['compile_log_sha256'] and re.search(
                    r'(?:region.*text.*overflowed|will not fit in region.*text)', log.read_text(errors='replace'), re.I),
                    'Linked no-fit proof differs')
            private.append(row)
            public.append({name: value for name, value in row.items() if name not in
                ('output', 'stream_sha256', 'pcm16_sha256', 'pwm_sha256', 'verification', 'compile_log_sha256')})
    comparisons = []
    for comparison in handoff['comparisons']:
        for irq in (0, 100):
            before, after = [indexed[comparison[name], irq] for name in ('rollback_chain', 'candidate_chain')]
            comparisons.append({**comparison, 'extra_irq_cycles': irq, 'both_passed': before['passed'] and after['passed'],
                'rollback_stream_bytes': before['stream_bytes'], 'candidate_stream_bytes': after['stream_bytes'],
                'data_saved_bytes': before['stream_bytes']-after['stream_bytes'],
                'complete_flash_saved_bytes': None if 'flash_bytes' not in before or 'flash_bytes' not in after else before['flash_bytes']-after['flash_bytes'],
                'program_flash_change_bytes': None if 'program_flash_bytes' not in before or 'program_flash_bytes' not in after else after['program_flash_bytes']-before['program_flash_bytes']})
    base.guard(epoch, handoff, raw, state, True)
    guard_recovery(base.load(args.recovery/'binding-private.json'))
    summary = dict(schema='lpx-v5-matched-search-rom-recovered-admission-v1', status='complete',
        unique_chains=len(handoff['chains']), changed_selected_cap_views=handoff['summary']['automatic_changed_selection_views'],
        unchanged_views_skipped=handoff['summary']['unchanged_selection_views_skipped'], rows=len(public),
        passed=sum(row['passed'] for row in public), new_images=sum(row['newly_built_and_simulated'] for row in public),
        reused_images=sum(row['reused_frozen_image'] for row in public),
        no_fit=sum(row['status'].startswith('no-fit') for row in public),
        timing_or_output_failures=sum(row['status'] == 'timing-or-output-failed' for row in public),
        verified_physical_samples=sum(row['samples'] for row in public if row['passed']), workers=workers,
        comparisons=comparisons, recovery=recovery, new_fits=0, perceptual_adoption=False,
        scope='Original finite ROM scope with one preserved pre-image filesystem failure and explicit suffix recovery; no repeated completed simulation, fitting, trimming or listening adoption.')
    source = dict(schema='lpx-v5-matched-search-rom-recovered-source-v1', producer_core_commit=handoff['producer_core_commit'],
        consumer_core_commit='5b4800f7', source_inventory=epoch.snapshot(), decoder_source_sha256=proof.env['source_sha256'],
        compiler=proof.env['compiler'], dependencies=proof.env['dependencies'],
        compile_source_sha256=proof.env['compile_source_sha256'], harness_sha256=proof.env['harness_sha256'], validation=proof.validation,
        dispatcher_sources_sha256={Path(name).name: digest for name, digest in handoff['dispatcher_sources_sha256'].items()},
        recovery_dispatcher_sha256=base.sha(THIS.read_bytes()),
        compiler_options_by_irq={str(irq): proof.recipe(base.bound_streams(handoff['chains'][0], epoch), irq)[2] for irq in (0, 100)},
        queue=256, prefill=192, explicit_asm=True, irq_loads=[0, 100], private_asset_bindings_exported=False)
    # Fresh aggregate targets have no competing reader; preserve all originals.
    for name, value in (('rows.json', dict(schema='lpx-v5-matched-search-rom-rows-v1', status='complete', rows=public)),
        ('results-private.json', dict(status='complete', handoff_sha256=base.sha(raw), rows=private, summary=summary)),
        ('summary.json', summary), ('source-runtime.json', source)):
        write_once(output/name, value)
    print(json.dumps({name: summary[name] for name in ('status', 'rows', 'passed', 'new_images', 'reused_images',
        'no_fit', 'timing_or_output_failures', 'verified_physical_samples', 'recovery')}), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'aggregate'))
    for name in ('source-root', 'handoff', 'campaign', 'recovery'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('source_root', 'handoff', 'campaign', 'recovery'):
        setattr(args, name, getattr(args, name).resolve())
    try:
        return run(args) if args.action == 'run' else aggregate(args)
    except Exception as error:
        path = args.recovery/(args.action+'-failure-private.json')
        write_once(path, dict(exception_type=type(error).__name__, traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed', action=args.action, exception_type=type(error).__name__)), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
