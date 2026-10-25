"""UM88: song-independent bounded control-tape codec (no MIDI binaries)."""
from collections import Counter

def _cost(stream,rules):
    return len(rules)*4+sum(1 if symbol<128 else 2 for symbol in stream)


def _candidate(data,limit,mode):
    stream=list(data);rules=[];depths=[0]*256
    best=(stream[:],rules[:],0);best_cost=_cost(stream,rules)
    while len(rules)<limit:
        counts=Counter(zip(stream,stream[1:]))
        candidates=[(n,p) for p,n in counts.items() if n>=5 and max(depths[p[0]],depths[p[1]])<12]
        if not candidates:break
        def rank(item):
            n,pair=item;width=sum(1 if symbol<128 else 2 for symbol in pair)
            priority=n if mode==0 else n*(width-1) if mode==1 else n*(width-2)-4
            return priority,n,tuple(-v for v in pair)
        _,pair=max(candidates,key=rank)
        out=[];at=0;code=256+len(rules)
        while at<len(stream):
            if at+1<len(stream) and (stream[at],stream[at+1])==pair:out.append(code);at+=2
            else:out.append(stream[at]);at+=1
        if len(stream)-len(out)<=2:break
        rules.append(pair);depths.append(1+max(depths[pair[0]],depths[pair[1]]));stream=out
        cost=_cost(stream,rules)
        if cost<best_cost:
            best=(stream[:],rules[:],max(depths));best_cost=cost
    return best


def grammar(data, limit=512):
    """Compare deterministic bounded grammars using their actual byte cost.

    Include the original frequency heuristic, two byte-width-aware heuristics
    and the unsqueezed stream. Keep the cheapest prefix of each search so the
    rule table never hides a net loss. Decoder, rule count and depth are unchanged.
    """
    if type(limit) is not int or not 0<=limit<=512:raise ValueError('Rule limit must be 0..512')
    data=list(data)
    if any(type(x) is not int or not 0<=x<=255 for x in data):raise ValueError('Expected command bytes')
    choices=[_candidate(data,limit,mode) for mode in range(3)]
    return min(choices,key=lambda item:_cost(item[0],item[1]))
