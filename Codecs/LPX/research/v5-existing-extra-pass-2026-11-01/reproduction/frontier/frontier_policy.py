"""Saved whole-chain size/joint frontier; no signal calculation or codec import."""
TOLERANCE=1e-12


def dominates(left,right):
    return (left['stream_bytes']<=right['stream_bytes'] and left['score']<=right['score']+TOLERANCE and
        (left['stream_bytes']<right['stream_bytes'] or left['score']<right['score']-TOLERANCE))


def equivalent(left,right):
    return left['stream_bytes']==right['stream_bytes'] and abs(left['score']-right['score'])<=TOLERANCE


def frontier(rows):
    """Keep every nondominated tuple, including distinct-byte rank ties."""
    return [row for row in rows if not any(dominates(other,row) for other in rows)]


def classify(point,prior):
    fitting=[row for row in prior if row['stream_bytes']<=point['stream_bytes']]
    best=None if not fitting else min(fitting,key=lambda r:(r['score'],r['stream_bytes'],r['order']))
    dominators=[r for r in prior if dominates(r,point)]
    ties=[r for r in prior if equivalent(r,point)]
    if not point['automatic_quality_eligible']:status='not-admissible'
    elif dominators:status='dominated-by-prior'
    elif ties:status='prior-frontier-rank-tie'
    else:status='extends-prior-frontier'
    return dict(status=status,prior_dominators=len(dominators),prior_rank_ties=len(ties),
        new_dominates_prior=sum(dominates(point,row) for row in prior) if point['automatic_quality_eligible'] else 0,
        best_prior_at_actual_bytes=None if best is None else best['origin'],
        joint_delta_at_actual_bytes=None if best is None else point['score']-best['score'])


def outcome(new,old):
    if new is None or old is None:
        return 'neither-admitted' if new is None and old is None else 'new-only' if old is None else 'prior-only'
    if abs(new['score']-old['score'])<=TOLERANCE:
        return 'equal-size-rank-tie' if new['stream_bytes']==old['stream_bytes'] else 'new-smaller-rank-tie' if new['stream_bytes']<old['stream_bytes'] else 'prior-smaller-rank-tie'
    return 'new-lower-joint' if new['score']<old['score'] else 'prior-lower-joint'


def failed(row,anchor,flags):
    reasons=[name for name,ok in flags.items() if not ok]
    for domain in ('pcm16','pwm8'):
        new,old=row['metrics'][domain],anchor['metrics'][domain]
        if new['error_energy']>old['error_energy']:reasons.append(domain+'_sse')
        if old['stoi'] is not None and (new['stoi'] is None or new['stoi']<old['stoi']-TOLERANCE):reasons.append(domain+'_stoi')
    return reasons


def numeric(row,anchor=None):
    result=dict(stream_bytes=row['stream_bytes'],score=row['score'],clipped_samples=row['clipped_samples'],
        pcm_period_coverage=row['voice']['within_tolerance_frames'],pwm_period_coverage=row['pwm_voice']['within_tolerance_frames'])
    for domain,label in (('pcm16','pcm'),('pwm8','pwm')):
        for key,short in (('error_energy','sse'),('ser_db','ser_db'),('stoi','stoi')):
            result[label+'_'+short]=row['metrics'][domain][key]
    if anchor is not None:
        result.update(byte_delta=row['stream_bytes']-anchor['stream_bytes'],joint_delta=row['score']-anchor['score'],
            pcm_sse_delta=row['metrics']['pcm16']['error_energy']-anchor['metrics']['pcm16']['error_energy'],
            pwm_sse_delta=row['metrics']['pwm8']['error_energy']-anchor['metrics']['pwm8']['error_energy'])
    return result
