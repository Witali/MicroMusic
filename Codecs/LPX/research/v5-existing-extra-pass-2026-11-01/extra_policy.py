"""Pure eligibility, fixed-slot whole recipes and complete-cap decisions."""
from __future__ import annotations

ARMS=('legacy','causal')


def eligible_groups(samples,extras):
    if type(samples) is not int or not 1<=samples<=64000:raise ValueError('Invalid reset length')
    if len(extras)!=8*((samples+319)//320) or any(not -8<=a<=7 or a and not 0<=p<40 for p,a in extras):
        raise ValueError('Invalid complete stored extra geometry')
    return [i for i,(position,amplitude) in enumerate(extras) if amplitude!=0 and i*40+position<samples]


def slot_views(catalogue,checkpoints):
    """Keep a missing slot distinct from a real baseline-valued checkpoint."""
    if not catalogue or catalogue[0]['id']!=0 or [r['id'] for r in catalogue]!=list(range(len(catalogue))):
        raise ValueError('The ordered catalogue must retain baseline id zero')
    if [r['slot'] for r in checkpoints]!=[1,2,3,4]:raise ValueError('Exactly four ordered explicit slots are required')
    interrupted=[r['id'] for r in catalogue if 'interrupted-final' in r['labels']]
    if len(interrupted)>1:raise ValueError('Only one final partial snapshot is allowed')
    complete=[r for r in checkpoints if r['status']=='complete']
    fallback=interrupted[0] if interrupted else complete[-1]['candidate_id'] if complete else 0
    chosen=[];provenance=[]
    for row in checkpoints:
        identifier=row['candidate_id'];ordinal=row['slot'];status=row['status']
        if type(identifier) is not int or not 0<=identifier<len(catalogue):raise ValueError('A slot names no captured candidate')
        label='checkpoint-'+str(ordinal)
        if status=='complete':
            if row['completed_active_groups']!=row['target_active_groups'] or label not in catalogue[identifier]['labels']:
                raise ValueError('A completed slot lacks actual coverage/publication')
            actual=identifier;reason=None
        elif status in ('partial_fallback','no_work'):
            if identifier!=fallback or label in catalogue[identifier]['labels']:
                raise ValueError('A fallback masquerades as completed coverage')
            actual=None;reason='interrupted_final' if interrupted else 'last_completed_snapshot' if complete else 'baseline_no_completed_snapshot'
            if status=='no_work' and (row['completed_active_groups'] or identifier):raise ValueError('No-work slots must honestly retain baseline')
        else:raise ValueError('Unknown checkpoint status')
        chosen.append(catalogue[identifier]['blob'])
        provenance.append(dict(**row,actual_id=actual,effective_id=identifier,fallback_reason=reason))
    return chosen,provenance


def whole_roles(baseline,locals):
    baseline=tuple(baseline)
    if [r['index'] for r in locals]!=list(range(len(baseline))):raise ValueError('Every original reset must participate once')
    result=[('baseline',baseline)]
    for slot in range(4):result.append(('coverage-slot-'+str(slot+1),tuple(r['slot_blobs'][slot] for r in locals)))
    for name in ('selected','raw'):
        result.append((name,None if any(r[name] is None for r in locals) else tuple(r[name] for r in locals)))
    for name in ('minimum-byte','minimum-sse'):
        key=(lambda p:(len(p['blob']),p['sse'],p['id'])) if name=='minimum-byte' else (lambda p:(p['sse'],len(p['blob']),p['id']))
        result.append((name,tuple(min(r['catalogue'],key=key)['blob'] for r in locals)))
    return result


def validate_caps(rows):
    if len(rows)!=12 or sorted(r['id'] for r in rows)!=list(range(12)):raise ValueError('Expected twelve distinct arm records')
    for row in rows:
        if [d['percent'] for d in row['decisions']]!=[100,95,90]:raise ValueError('Each real row needs exactly ordered 100/95/90 views')
    return sum(len(r['decisions']) for r in rows)
