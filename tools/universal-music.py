"""UM88: song-independent bounded control-tape codec (no MIDI binaries)."""
from collections import Counter

def grammar(data, limit=512):
    stream=list(data);rules=[];depths=[0]*256
    while len(rules)<limit:
        counts=Counter(zip(stream,stream[1:]))
        candidates=[(n,p) for p,n in counts.items() if n>=5 and max(depths[p[0]],depths[p[1]])<12]
        if not candidates:break
        _,pair=max(candidates,key=lambda x:(x[0],tuple(-v for v in x[1])))
        out=[];at=0;code=256+len(rules)
        while at<len(stream):
            if at+1<len(stream) and (stream[at],stream[at+1])==pair:out.append(code);at+=2
            else:out.append(stream[at]);at+=1
        if len(stream)-len(out)<=2:break
        rules.append(pair);depths.append(1+max(depths[pair[0]],depths[pair[1]]));stream=out
    return stream,rules,max(depths)
