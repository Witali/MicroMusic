"""Pure retained-history selection; no decoder or search imports."""
from __future__ import annotations

import math
from numbers import Integral


def prefix_pool_ids(report, depth):
    """IDs visible after one common count of completed local operators."""
    if isinstance(depth, bool) or not isinstance(depth, Integral) or not 0 <= depth <= 4:
        raise ValueError('Expected a common prefix depth in 0..4')
    rows, stages = report['candidates'], report['stages']
    if not rows or len(stages) > 4:
        raise ValueError('Expected a nonempty bounded saved candidate pool')
    for index, row in enumerate(rows):
        if row['id'] != index or not math.isfinite(row['score']) or row['file_bytes'] < 1:
            raise ValueError('Invalid saved candidate row')
    visible = {row['id'] for row in rows if row['origin'] in ('control', 'seed')}
    if 0 not in visible or rows[0]['origin'] != 'control':
        raise ValueError('The saved admission anchor must be initially visible')
    prefixes = [set(visible)]
    for stage in stages:
        if stage['parent'] not in visible:
            raise ValueError('A stage depends on a future candidate')
        for index in stage['outputs']:
            if isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index < len(rows):
                raise ValueError('A stage refers to a missing candidate')
            if index not in visible and rows[index]['origin'] != stage['operator']:
                raise ValueError('A new candidate has the wrong producing operator')
            visible.add(index)
        prefixes.append(set(visible))
    if visible != set(range(len(rows))):
        raise ValueError('The final pool contains an unintroduced candidate')
    return sorted(prefixes[min(int(depth), len(stages))])


def ranked_prefix_ids(report, depth):
    """Apply audited static eligibility and the frozen score/bytes/ID order."""
    rows = [report['candidates'][index] for index in prefix_pool_ids(report, depth)]
    cap = report['complete_byte_cap']
    fitting = [row for row in rows if row['file_bytes'] <= cap]
    for row in rows:
        if 'fits_complete_cap' in row and row['fits_complete_cap'] != (row['file_bytes'] <= cap):
            raise ValueError('Saved feasibility contradicts actual row bytes')
    eligible = [row for row in fitting if row['admissible']]
    key = lambda row: (row['score'], row['file_bytes'], row['id'])
    return {label: None if not choices else min(choices, key=key)['id']
            for label, choices in (('selected', eligible), ('raw', fitting))}


def common_prefix_descriptors(record, depth, label):
    """Full ordered snapshot; all resets share one depth, absent stays absent."""
    if label not in ('selected', 'raw'):
        raise ValueError('Expected selected or raw prefix view')
    searches = record['segment_searches']
    if [s['index'] for s in searches] != list(range(len(searches))):
        raise ValueError('Prefix replay requires every ordered reset')
    result = []
    for search in searches:
        identifier = ranked_prefix_ids(search['report'], depth)[label]
        if identifier is None:
            return None
        meta = search['pool'][identifier]
        if meta['id'] != identifier:
            raise ValueError('Saved sink order differs from candidate IDs')
        result.append(meta)
    return result


def retain_distinct(chains):
    """Deduplicate exact ordered reset bytes and retain every source label."""
    unique, positions = [], {}
    for label, blobs in chains:
        if blobs is None:
            continue
        key = tuple(bytes(blob) for blob in blobs)
        if not key:
            raise ValueError('A whole chain cannot be empty')
        if key in positions:
            unique[positions[key]]['labels'].append(label)
        else:
            positions[key] = len(unique)
            unique.append(dict(id=len(unique), labels=[label], blobs=key,
                               stream_bytes=sum(map(len, key))))
    return unique


def choose_budget(rows, original_bytes, percent):
    """Stable whole-pool selection; rows use exact complete-chain byte cost."""
    if (isinstance(original_bytes, bool) or not isinstance(original_bytes, Integral)
            or original_bytes < 22 or percent not in (100, 95, 90)):
        raise ValueError('Invalid original whole cap or percentage')
    cap = int(original_bytes) * percent // 100
    fit = [row for row in rows if row['stream_bytes'] <= cap]
    good = [row for row in fit if row['automatic_quality_eligible']]
    key = lambda row: (row['score'], row['stream_bytes'], row['id'])
    return dict(percent=percent, cap=cap,
        selected_id=None if not good else min(good, key=key)['id'],
        raw_id=None if not fit else min(fit, key=key)['id'],
        fitting_chains=len(fit), eligible_chains=len(good),
        no_fit=not fit, no_automatic_admission=not good)


def assert_incumbents_retained(rows, decision, incumbent_ids):
    """A deeper retained pool cannot lose any known feasible admitted winner."""
    old = [rows[index] for index in incumbent_ids if index is not None
           and rows[index]['stream_bytes'] <= decision['cap']
           and rows[index]['automatic_quality_eligible']]
    if not old:
        return
    selected = decision['selected_id']
    if selected is None:
        raise AssertionError('A known feasible admitted chain disappeared')
    chosen = rows[selected]
    if any((chosen['score'], chosen['stream_bytes']) > (row['score'], row['stream_bytes']) for row in old):
        raise AssertionError('Retained selection is worse than an admitted incumbent')
