"""UM88: song-independent bounded control-tape codec (no MIDI binaries)."""
from collections import Counter
from itertools import groupby

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


def _nine_cost(stream,rules):
    return (len(rules)*18+7)//8+(len(stream)*9+7)//8


def _compact_candidate(data,limit,mode):
    stream=list(data);rules=[];depths=[0]*256;lengths=[1]*256
    best=(stream[:],rules[:],0);best_cost=_nine_cost(stream,rules)
    while len(rules)<limit:
        counts=Counter(zip(stream,stream[1:]))
        # Overlapping AA pairs cannot all be replaced. Count the actual greedy
        # substitutions, so an unprofitable run cannot end the whole search.
        for symbol,run in groupby(stream):
            size=sum(1 for _ in run)
            if size>2:counts[(symbol,symbol)]-=(size-1)//2
        candidates=[(n,p) for p,n in counts.items() if n>=3 and max(depths[p[0]],depths[p[1]])<12]
        if not candidates:break
        def rank(item):
            n,p=item
            tie=0 if mode==0 else -max(depths[p[0]],depths[p[1]]) if mode==1 else lengths[p[0]]+lengths[p[1]]
            return n,tie,tuple(-v for v in p)
        _,pair=max(candidates,key=rank)
        out=[];at=0;code=256+len(rules)
        while at<len(stream):
            if at+1<len(stream) and (stream[at],stream[at+1])==pair:out.append(code);at+=2
            else:out.append(stream[at]);at+=1
        if len(stream)-len(out)<=2:raise AssertionError('Non-overlapping pair count disagrees')
        rules.append(pair);depths.append(1+max(depths[pair[0]],depths[pair[1]]))
        lengths.append(lengths[pair[0]]+lengths[pair[1]]);stream=out
        cost=_nine_cost(stream,rules)
        if cost<best_cost:
            best=(stream[:],rules[:],max(depths));best_cost=cost
    return best


def _pack9(symbols):
    output=bytearray();bits=0;available=0
    for symbol in symbols:
        if type(symbol) is not int or not 0<=symbol<512:raise ValueError('Expected 9-bit symbols')
        bits|=symbol<<available;available+=9
        while available>=8:
            output.append(bits&255);bits>>=8;available-=8
    if available:output.append(bits)
    return bytes(output)


def pack_grammar(data,limit=512):
    """Bounded phrase dictionary with a dense alphabet and 9-bit references.

    Command bytes and their arguments remain exact. Only their storage changes:
    terminal IDs index the byte alphabet; later IDs invoke binary phrase rules.
    All rule symbols and stream symbols use little-endian 9-bit fields.
    """
    if type(limit) is not int or not 0<=limit<=512:raise ValueError('Rule limit must be 0..512')
    data=list(data)
    if not data or any(type(x) is not int or not 0<=x<=255 for x in data):raise ValueError('Expected nonempty command bytes')
    alphabet=bytes(sorted(set(data)));count=len(alphabet)
    choices=[_compact_candidate(data,min(limit,512-count),mode) for mode in range(3)]
    stream,rules,depth=min(choices,key=lambda item:(_nine_cost(item[0],item[1]),len(item[1]),item[2]))
    lookup={byte:index for index,byte in enumerate(alphabet)}
    dense=lambda symbol:lookup[symbol] if symbol<256 else count+symbol-256
    rules=[tuple(dense(symbol) for symbol in pair) for pair in rules]
    stream=[dense(symbol) for symbol in stream]
    rule_data=_pack9(symbol for pair in rules for symbol in pair);stream_data=_pack9(stream)
    result=dict(format=9,alphabet=alphabet,rules=rules,stream=stream,ruleData=rule_data,
                streamData=stream_data,depth=depth,grammarBytes=count+len(rule_data)+len(stream_data))
    if unpack_grammar(result)!=data:raise AssertionError('Packed grammar changed command bytes')
    return result


def pack_fast_grammar(data,limit=512):
    """Original byte/uint16 dictionary layout, with the compact API shape.

    This representation trades Flash for cheaper rule lookup and symbol reads.
    It preserves the same bounded phrase dictionary and exact command bytes.
    """
    data=list(data)
    if not data or any(type(x) is not int or not 0<=x<=255 for x in data):raise ValueError('Expected nonempty command bytes')
    stream,rules,depth=grammar(data,limit)
    rule_data=bytes(byte for pair in rules for symbol in pair for byte in (symbol&255,symbol>>8))
    stream_data=bytearray()
    for symbol in stream:
        if symbol<128:stream_data.append(symbol)
        else:stream_data.extend((128|(symbol>>8),symbol&255))
    result=dict(format=0,alphabet=b'',rules=rules,stream=stream,ruleData=rule_data,
                streamData=bytes(stream_data),depth=depth,grammarBytes=len(rule_data)+len(stream_data))
    if unpack_grammar(result)!=data:raise AssertionError('Fast grammar changed command bytes')
    return result


def unpack_grammar(packed):
    """Independently decode serialized fast-0 or compact-9 dictionary fields."""
    format_=packed['format']
    if type(format_) is not int or format_ not in (0,9):raise ValueError('Expected UM88 grammar format 0 or 9')
    alphabet=bytes(packed['alphabet']);rules_count=len(packed['rules']);stream_count=len(packed['stream'])
    def fields(data,number):
        data=bytes(data)
        if len(data)!=(number*9+7)//8:raise ValueError('Invalid packed symbol length')
        if number*9%8 and data[-1]>>(number*9%8):raise ValueError('Nonzero symbol padding')
        values=[]
        for index in range(number):
            bit=index*9;at=bit>>3
            values.append(((data[at]|data[at+1]<<8)>>(bit&7))&511)
        return values
    if format_==9:
        count=len(alphabet)
        if not 1<=count<=256 or len(set(alphabet))!=count or count+rules_count>512:raise ValueError('Invalid compact alphabet')
        pairs=fields(packed['ruleData'],rules_count*2)
        symbols=fields(packed['streamData'],stream_count)
    else:
        count=256
        if alphabet or not 0<=rules_count<=512:raise ValueError('Invalid fast dictionary')
        data=bytes(packed['ruleData'])
        if len(data)!=rules_count*4:raise ValueError('Invalid fast rule length')
        pairs=[data[at]|data[at+1]<<8 for at in range(0,len(data),2)]
        data=bytes(packed['streamData']);symbols=[];at=0
        while at<len(data):
            first=data[at];at+=1
            if first<128:symbols.append(first)
            else:
                if at>=len(data):raise ValueError('Truncated fast symbol')
                value=((first&127)<<8)|data[at];at+=1
                if value<128:raise ValueError('Noncanonical fast symbol')
                symbols.append(value)
        if len(symbols)!=stream_count:raise ValueError('Invalid fast stream length')
    rules=[tuple(pairs[i:i+2]) for i in range(0,len(pairs),2)]
    depths=[0]*count
    for index,pair in enumerate(rules):
        if any(symbol>=count+index for symbol in pair):raise ValueError('Rule must refer to an earlier symbol')
        depth=1+max(depths[pair[0]],depths[pair[1]])
        if depth>12:raise ValueError('Grammar depth exceeds 12')
        depths.append(depth)
    output=[]
    for symbol in symbols:
        pending=[symbol]
        while pending:
            if len(pending)>13:raise ValueError('Grammar exceeds pending-symbol budget')
            code=pending.pop()
            if code<count:output.append(alphabet[code] if format_==9 else code)
            elif code<count+rules_count:
                a,b=rules[code-count];pending.extend((b,a))
            else:raise ValueError('Rule reference out of range')
    return output
