"""Replay bounded local search history into retained whole-reset snapshots.

Promoted from the measured v5-prefix-retention experiment. This module owns
causal pool visibility, not quality measurement or decoder state. Every reset
uses one common completed-call depth; unsearched resets stay at the baseline.
"""
from __future__ import annotations

import math
from numbers import Integral


def prefix_pool_ids(report, depth):
    """Return IDs visible after depth calls, validating the complete history."""
    if isinstance(depth, bool) or not isinstance(depth, Integral) or not 0 <= depth <= 32:
        raise ValueError('Expected a common prefix depth in 0..32')
    rows, stages = report['candidates'], report['stages']
    if not rows or len(stages) > 32:
        raise ValueError('Expected a nonempty bounded candidate pool')
    for index, row in enumerate(rows):
        if (type(row['id']) is not int or row['id'] != index
                or not math.isfinite(row['score'])
                or type(row['file_bytes']) is not int or row['file_bytes'] < 22):
            raise ValueError('Invalid candidate row')
    visible = {row['id'] for row in rows if row['origin'] in ('control', 'seed')}
    if rows[0]['origin'] != 'control':
        raise ValueError('The admission anchor must be initially visible')
    prefixes = [set(visible)]
    for stage in stages:
        parent = stage['parent']
        if type(parent) is not int or parent not in visible:
            raise ValueError('A stage depends on a future candidate')
        for index in stage['outputs']:
            if type(index) is not int or not 0 <= index < len(rows):
                raise ValueError('A stage refers to a missing candidate')
            if index not in visible and rows[index]['origin'] != stage['operator']:
                raise ValueError('A new candidate has the wrong producing operator')
            visible.add(index)
        prefixes.append(set(visible))
    if visible != set(range(len(rows))):
        raise ValueError('The final pool contains an unintroduced candidate')
    return sorted(prefixes[min(int(depth), len(stages))])


def ranked_prefix_ids(report, depth):
    """Recover local selected/raw snapshots; whole admission is independent."""
    rows = [report['candidates'][i] for i in prefix_pool_ids(report, depth)]
    cap = report['complete_byte_cap']
    fitting = []
    for row in rows:
        fits = row['file_bytes'] <= cap
        if row['fits_complete_cap'] != fits:
            raise ValueError('Local feasibility contradicts serialized byte cost')
        if fits and row.get('fits_flash_cap', True):
            fitting.append(row)
    eligible = [row for row in fitting if row['admissible']]
    key = lambda row: (row['score'], row['file_bytes'], row['id'])
    return {label: None if not choices else min(choices, key=key)['id']
            for label, choices in (('selected', eligible), ('raw', fitting))}


def retained_prefixes(baseline, histories, incumbents=()):
    """Deduplicate exact ordered bytes, retaining baseline and every label.

    A history contains reset index, actual pool bytes in report ID order, and
    the local controller report. Partial histories never replace other resets.
    Reports only specify snapshot recipes; their whole quality is not trusted.
    """
    baseline = tuple(baseline)
    histories = list(histories)
    indices = [h['index'] for h in histories]
    if (any(type(i) is not int or not 0 <= i < len(baseline) for i in indices)
            or indices != sorted(set(indices))):
        raise ValueError('Expected unique ordered searched reset indices')
    for history in histories:
        rows, pool = history['report']['candidates'], history['pool']
        if isinstance(pool, (bytes, bytearray, str)) or len(rows) != len(pool):
            raise ValueError('Candidate sink count differs from the report')
        prefix_pool_ids(history['report'], 32)
        if any(len(blob) != row['file_bytes'] for blob, row in zip(pool, rows)):
            raise ValueError('Candidate byte cost differs from its actual stream')
    depth = max((len(h['report']['stages']) for h in histories), default=0)
    choices = [('control', baseline)]
    choices.extend(('incumbent-%d' % i, blobs) for i, blobs in enumerate(incumbents))
    for count in range(depth + 1):
        for label in ('selected', 'raw'):
            blobs = list(baseline)
            for history in histories:
                identifier = ranked_prefix_ids(history['report'], count)[label]
                if identifier is None:
                    blobs = None
                    break
                blobs[history['index']] = history['pool'][identifier]
            choices.append(('prefix-%d-%s' % (count, label), blobs))
    unique, positions = [], {}
    for label, blobs in choices:
        if blobs is None:
            continue
        if isinstance(blobs, (bytes, bytearray, str)):
            raise ValueError('Expected ordered reset streams in each incumbent')
        key = tuple(bytes(blob) for blob in blobs)
        if len(key) != len(baseline):
            raise ValueError('A retained chain changed the number of resets')
        if key in positions:
            unique[positions[key]]['labels'].append(label)
        else:
            positions[key] = len(unique)
            unique.append(dict(id=len(unique), labels=[label], streams=key,
                               stream_bytes=sum(map(len, key))))
    return unique
