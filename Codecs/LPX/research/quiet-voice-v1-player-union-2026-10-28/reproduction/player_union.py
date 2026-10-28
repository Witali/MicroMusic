"""Derive only audited, changed selected chains; no new fit or selection rule."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from admit import Epoch, canonical, sha


def main(args):
    epoch = Epoch(args.source_root)
    audit_path = args.audit / 'audit-private.json'
    audit = json.loads(audit_path.read_text())
    summary = json.loads((args.audit / 'audit.json').read_text())
    context = json.loads((args.audit / 'context-audit.json').read_text())
    binding_raw = (args.study / 'binding-private.json').read_bytes()
    binding = json.loads(binding_raw)
    assert audit['status'] == summary['status'] == context['status'] == 'passed'
    assert audit['binding_sha256'] == sha(binding_raw)
    prepared_raw = args.prepared.read_bytes()
    prepared = json.loads(prepared_raw)
    assert prepared['source_inventory'] == epoch.snapshot()
    registry = {}
    comparisons = {}
    def register(entry, role):
        streams = []
        position = 0
        for index, part in enumerate(entry['segments']):
            blob = Path(part['path']).read_bytes()
            assert sha(blob) == part['stream_sha256'] and len(blob) == part['file_bytes']
            assert part['index'] == index and part['start'] == position and part['profile'] == entry['profile']
            assert epoch.modules['speech_compact'].unpack(blob)[:2] == (part['samples'], entry['profile'])
            position += part['samples']; streams.append(blob)
        assert position == entry['samples'] and sum(map(len, streams)) == entry['file_bytes']
        key = tuple(sha(blob) for blob in streams)
        if key not in registry:
            registry[key] = {'id': 'chain-%03d' % (len(registry) + 1), 'entry': entry, 'roles': []}
        else:
            previous = registry[key]['entry']
            assert previous['samples'] == entry['samples'] and previous['profile'] == entry['profile'] and previous['file_bytes'] == entry['file_bytes']
            assert previous['pcm16_sha256'] == entry['pcm16_sha256'] and previous['pwm_sha256'] == entry['pwm_sha256']
        if role not in registry[key]['roles']:
            registry[key]['roles'].append(role)
        return registry[key]['id'], key
    changed_rows = 0
    unchanged_rows = 0
    for selection in audit['selections']:
        if not selection['changed_from_original_level_control']:
            unchanged_rows += 1
            continue
        changed_rows += 1
        record = binding['records'][selection['record_index']]
        original = dict(selection['original'])
        original.update(pcm16_sha256=record['baseline_pcm16_sha256'], pwm_sha256=record['baseline_pwm_sha256'])
        candidate = {key: selection['candidate'][key] for key in ('samples', 'segments', 'pcm16_sha256', 'pwm_sha256')}
        candidate.update(profile=selection['profile'], file_bytes=selection['candidate']['stream_bytes'])
        old_id, old_key = register(original, 'original-level-control')
        new_id, new_key = register(candidate, 'changed-selected-candidate')
        assert old_key != new_key
        key = (selection['record_index'], selection['mode'], old_id, new_id)
        if key not in comparisons:
            comparisons[key] = {'id': 'comparison-%03d' % (len(comparisons) + 1), 'original_chain': old_id, 'candidate_chain': new_id,
                'profile': selection['profile'], 'source_ordinal': selection['source_ordinal'], 'record_index': selection['record_index'],
                'mode': selection['mode'], 'reference_domain': 'auto-declared-target' if selection['mode'] == 'auto-quiet' else 'preserve-original',
                'old_playback_gain': 1, 'new_input_gain': selection['level']['gain'],
                'quality_adopted_at_frozen_study': selection['mode'] == 'preserve',
                'eligible_under_frozen_whole_chain_gates': selection['candidate']['automatic_quality_eligible'],
                'changed_from_declared_target_control': selection['changed_from_declared_control'],
                'quality_scope': 'Whole declared-target/control PCM/PWM/voice/objective floors; no original-level quality claim for changed gain. Playback does not activate policy.',
                'selections': []}
        comparisons[key]['selections'].append({key: selection[key] for key in ('percent', 'cap', 'role', 'split', 'cohort', 'targeted')})
    result = {'schema': 'lpx-quiet-voice-player-union-private-v1', 'source_root': str(epoch.root),
        'study_binding_sha256': sha(binding_raw), 'audit_private_sha256': sha(audit_path.read_bytes()),
        'audit_sha256': sha((args.audit / 'audit.json').read_bytes()), 'context_audit_sha256': sha((args.audit / 'context-audit.json').read_bytes()),
        'preparation_sha256': sha(prepared_raw), 'source_inventory': prepared['source_inventory'],
        'chains': list(registry.values()), 'comparisons': list(comparisons.values()),
        'changed_selection_rows': changed_rows, 'unchanged_selected_rows_not_measured': unchanged_rows,
        'scope': 'Exact-chain union of audited changed selections across 100/95/90 caps versus original-level controls. Every chain measured/reused once per IRQ load. Separate mode/gain/whole quality scope; no refit or policy promotion.'}
    epoch.save(args.output, result)
    print(json.dumps({'chains': len(registry), 'comparisons': len(comparisons), 'changed_selection_rows': changed_rows,
        'unchanged_selected_rows_not_measured': unchanged_rows, 'candidate_chains': sum('changed-selected-candidate' in value['roles'] for value in registry.values()),
        'original_chains': sum('original-level-control' in value['roles'] for value in registry.values())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'study', 'audit', 'prepared', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
