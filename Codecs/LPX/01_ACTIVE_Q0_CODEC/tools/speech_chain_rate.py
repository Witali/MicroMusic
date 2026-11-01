"""Exact additive PCM-SSE/rate allocation over fixed serialized reset pools.

This module does no fitting, decoding or quality admission. Its caller must
verify each stream's geometry, reference, native output and integer local SSE.
Whole PWM/STOI/pitch/voice/noise gates remain separate and nonadditive.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral


@dataclass(frozen=True)
class ChainRatePoint:
    ids: tuple
    file_bytes: int
    sse: int


@dataclass(frozen=True)
class ChainRateResult:
    status: str
    exact: bool
    best: ChainRatePoint | None
    frontier: tuple
    protected: tuple
    work: dict


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError('Expected integer ' + name)
    return int(value)


def allocate_exact_sse(pools, max_bytes, *, baseline_ids, protected_chains=(),
                       max_states=250000, max_transitions=10000000,
                       checkpoint=None, on_candidate=None):
    """Return the complete finite-pool (actual bytes, integer SSE) frontier.

    Each pool row supplies nonnegative stable integer ``id``, actual nonempty
    ``stream: bytes`` and verified nonnegative integer ``sse``. IDs are local
    to a reset. Duplicate bytes must have the same SSE. All sums use Python
    integers; equal byte/SSE points prefer lexicographically smaller ID tuples.

    Baseline/protected tuples are retained independently, including oversized
    or SSE-dominated choices. They do not seed, prune or consume DP work.
    A resource limit gives exact=False, best=None and frontier=(), never a
    partial-prefix winner or a no-fit claim. ``on_candidate`` immediately
    receives each improved feasible final-layer byte state, before the next
    checkpoint or state-limit guard, so completed full choices can survive an
    interruption. These callbacks are candidates, not admitted quality results.
    Checkpoint/callback exceptions propagate; no partial result is relabeled.

    max_states bounds distinct byte states in any working layer, before
    dominance pruning. max_transitions bounds all visited prefix/option pairs,
    including those pruned by the minimum remaining completion size. Neither
    limit silently samples or approximates the exact frontier.
    """
    max_bytes = _integer(max_bytes, 'byte cap')
    max_states = _integer(max_states, 'state limit', 1)
    max_transitions = _integer(max_transitions, 'transition limit', 1)
    if any(value is not None and not callable(value) for value in (checkpoint,on_candidate)):
        raise ValueError('Expected callable checkpoint/candidate callback')
    choices, lookups = [], []
    for supplied in pools:
        lookup, by_stream = {}, {}
        for row in supplied:
            identifier = _integer(row['id'], 'candidate ID')
            score = _integer(row['sse'], 'PCM SSE')
            stream = row['stream']
            if not isinstance(stream, bytes) or not stream:
                raise ValueError('Expected actual nonempty serialized bytes')
            if identifier in lookup:
                raise ValueError('Duplicate candidate ID within one reset')
            lookup[identifier] = (len(stream), score)
            if stream in by_stream and by_stream[stream][1] != score:
                raise ValueError('Identical serialized bytes have inconsistent SSE')
            previous = by_stream.get(stream)
            if previous is None or identifier < previous[0]:
                by_stream[stream] = (identifier, score, len(stream))
        if not lookup:
            raise ValueError('Expected nonempty candidate pool for every reset')
        lookups.append(lookup)
        choices.append(sorted(by_stream.values()))
    if not choices:
        raise ValueError('Expected at least one reset pool')

    def point(ids):
        ids = tuple(_integer(i, 'chain candidate ID') for i in ids)
        if len(ids) != len(lookups) or any(i not in pool for i,pool in zip(ids,lookups)):
            raise ValueError('Protected chain must name one existing option per reset')
        return ChainRatePoint(ids, sum(pool[i][0] for i,pool in zip(ids,lookups)),
                              sum(pool[i][1] for i,pool in zip(ids,lookups)))
    protected = {}
    for ids in (baseline_ids, *protected_chains):
        value = point(ids)
        protected.setdefault(value.ids,value)
    protected = tuple(protected.values())
    work = dict(transitions=0, states_created=0, peak_states=0,
                processed_resets=0, completion_size_pruned=0,
                dominated_states_removed=0, completed_candidates=0)

    def result(status, exact, states=None):
        frontier = tuple(ChainRatePoint(ids, size, score) for size,(score,ids) in
                         sorted(states.items())) if states is not None else ()
        best = min(frontier,key=lambda p:(p.sse,p.file_bytes,p.ids)) if frontier else None
        return ChainRateResult(status,exact,best,frontier,protected,work.copy())

    remaining = [0]*(len(choices)+1)
    for depth in range(len(choices)-1,-1,-1):
        remaining[depth] = remaining[depth+1]+min(c[2] for c in choices[depth])
    if remaining[0] > max_bytes:
        return result('no_pool_combination_fits',True,{})
    states = {0:(0,())}
    work.update(states_created=1,peak_states=1)
    for depth,pool in enumerate(choices):
        expanded = {}
        final = depth+1 == len(choices)
        for size,(score,ids) in sorted(states.items()):
            for identifier,local_sse,local_bytes in pool:
                if checkpoint is not None:
                    checkpoint()
                if work['transitions'] >= max_transitions:
                    return result('transition_limit',False)
                work['transitions'] += 1
                new_size = size+local_bytes
                if new_size+remaining[depth+1] > max_bytes:
                    work['completion_size_pruned'] += 1
                    continue
                candidate = (score+local_sse,ids+(identifier,))
                if new_size in expanded and expanded[new_size] <= candidate:
                    continue
                if final:
                    work['completed_candidates'] += 1
                    if on_candidate is not None:
                        on_candidate(ChainRatePoint(candidate[1],new_size,candidate[0]))
                if new_size not in expanded:
                    if len(expanded) >= max_states:
                        return result('state_limit',False)
                    work['states_created'] += 1
                expanded[new_size] = candidate
                work['peak_states'] = max(work['peak_states'],len(expanded))
        # A cheaper prefix with no larger SSE dominates for every possible
        # remaining suffix. This proof concerns additive PCM SSE and bytes only.
        states, best_score = {}, None
        for size,candidate in sorted(expanded.items()):
            if best_score is None or candidate[0] < best_score:
                states[size] = candidate
                best_score = candidate[0]
        work['dominated_states_removed'] += len(expanded)-len(states)
        work['processed_resets'] += 1
    return result('complete',True,states)
