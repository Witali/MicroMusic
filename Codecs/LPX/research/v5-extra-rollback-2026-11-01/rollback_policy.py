"""Pure common coverage, protected-pair acceptance and bounded tuple retention."""
from __future__ import annotations
import math

ARMS=('continue','rollback')
GATES=('old_pcm_pwm_floors_passed','clipped_sample_floor_passed',
    'pcm_period_coverage_floor_passed','pwm_period_coverage_floor_passed','joint_objective_nonregression')


def coverage_targets(initial_eligible):
    if type(initial_eligible) is not int or not 0<=initial_eligible<=1600:
        raise ValueError('Expected the initial played-active count for one bounded reset')
    return tuple((initial_eligible*k+3)//4 for k in range(1,5))


def rank(row):
    score,size=row['score'],row['stream_bytes']
    if type(score) not in (int,float) or not math.isfinite(score) or type(size) is not int or not 22<=size<=255*65535:
        raise ValueError('Expected a finite measured whole score and actual serialized byte count')
    return score,size


def accept_block(candidate,original_anchor_gates,protected):
    """Exact canonical score/byte ordering; no descriptive tolerance here."""
    if set(original_anchor_gates)!=set(GATES) or any(type(v) is not bool for v in original_anchor_gates.values()):
        raise ValueError('Every unchanged original-anchor gate must be explicit')
    original_ok=all(original_anchor_gates.values())
    not_worse=rank(candidate)<=rank(protected)
    return dict(accepted=original_ok and not_worse,original_anchor_gates_passed=original_ok,
        protected_pair_not_worse=not_worse,candidate_pair=rank(candidate),protected_pair=rank(protected))


def retained_attempts(attempts):
    """Reconstruct baseline plus up to four complete stage proposals exactly.

    Every event is retained even when it names an existing exact ordered tuple.
    This recipe never constructs a combination of different stages/resets.
    Caller I/O must persist each new tuple before producer/metric continuation.
    """
    if not isinstance(attempts,(tuple,list)) or not 1<=len(attempts)<=5 or [slot for slot,parts in attempts]!=list(range(len(attempts))):
        raise ValueError('Require baseline slot zero then at most four consecutive stages')
    catalogue=[];positions={};events=[];resets=None
    for slot,parts in attempts:
        if not isinstance(parts,(tuple,list)):raise ValueError('Expected an ordered complete reset tuple')
        if not parts or any(not isinstance(p,(bytes,bytearray)) or not 22<=len(p)<=65535 for p in parts):
            raise ValueError('Expected complete bounded serialized reset bytes')
        actual=tuple(bytes(p) for p in parts)
        if resets is None:resets=len(actual)
        if len(actual)!=resets:raise ValueError('A proposal changed the original reset count')
        fresh=actual not in positions
        if fresh:
            positions[actual]=len(catalogue)
            catalogue.append(dict(id=len(catalogue),parts=actual,stream_bytes=sum(map(len,actual)),slots=[]))
        identifier=positions[actual];catalogue[identifier]['slots'].append(slot)
        events.append(dict(slot=slot,candidate_id=identifier,new_tuple=fresh))
    return catalogue,events


def validate_contexts(baselines):
    if len(baselines)!=2 or {b['source_ordinal'] for b in baselines}!={20,42}:
        raise ValueError('Require exactly the predeclared two original speech contexts')
    resets=0
    for base in baselines:
        expected=1 if base['source_ordinal']==20 else 5
        if base['profile']!=4 or base['nonspeech'] is not False or len(base['segments'])!=expected:
            raise ValueError('P4 speech/reset scope differs')
        at=0;size=0
        for index,meta in enumerate(base['segments']):
            if (meta['index']!=index or meta['start']!=at or meta['profile']!=4 or
                    type(meta['samples']) is not int or not 1<=meta['samples']<=64000 or
                    type(meta['file_bytes']) is not int or not 22<=meta['file_bytes']<=65535):
                raise ValueError('Original complete reset geometry or byte cost differs')
            at+=meta['samples'];size+=meta['file_bytes']
        if at!=base['samples'] or size!=base['stream_bytes']:raise ValueError('The complete original recording differs')
        resets+=expected
    if resets!=6:raise ValueError('Expected exactly six reset contexts per arm')
    return dict(contexts=2,arm_records=4,reset_pass_instances=12,stage_events=16,max_distinct_whole_attempts=20,cap_views=12)
