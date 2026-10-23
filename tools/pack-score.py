"""Lossless phrase packing for the existing AVR playlist decoder.

No new opcodes or runtime decompressor. Search repeated command phrases,
use shortest-path parsing, and share suffixes in physical Flash storage.
Dictionary selection is a deterministic heuristic, not a proof of the global
smallest grammar. Each result is checked against the original command stream.
"""
from collections import defaultdict,Counter
import hashlib
import json


def atoms(stream):
    result=[];pending=bytearray()
    for token in stream:
        if token==255:raise ValueError('Section delimiters must be removed before packing')
        pending.append(token)
        if token<224:result.append(bytes(pending));pending.clear()
    if pending:raise ValueError('A section must end with a timed note/rest/hold')
    return result


def layout(pieces):
    unique=list(dict.fromkeys(pieces))
    # A reference may start inside a longer section and reuse its terminator.
    roots=[s for s in unique if not any(len(t)>len(s) and t.endswith(s) for t in unique)]
    roots.sort(key=lambda s:unique.index(s))
    def place(order):
        offsets={};storage=bytearray()
        for root in order:
            start=len(storage);storage.extend(root);storage.append(255)
            for s in unique:
                if s not in offsets and root.endswith(s):offsets[s]=start+len(root)-len(s)
        return offsets,storage
    offsets,storage=place(roots)
    if max(offsets.values(),default=0)>255:
        # Only playlist entry addresses are eight bits; Z/LPM may continue
        # beyond byte255. All starts in earlier roots precede the last root's
        # own start, so the largest entry belongs to that last root. A suffix
        # shared with another root is already assigned before we reach it.
        # Thus only exclusive suffixes constrain a root's final tail budget.
        exclusive_delta={root:0 for root in roots}
        for word in unique:
            owner=None
            for root in roots:
                if root.endswith(word):
                    if owner is not None:
                        owner=None;break
                    owner=root
            if owner is not None:
                exclusive_delta[owner]=max(exclusive_delta[owner],len(owner)-len(word))
        # For total storage T, max entry = T - (len(last)+1-max_delta).
        # Choose its minimum over all root orders. Preserve the current last
        # root on ties; valid existing layouts never enter this branch.
        last=max(roots,key=lambda root:(len(root)+1-exclusive_delta[root],root==roots[-1]))
        if last!=roots[-1]:offsets,storage=place([root for root in roots if root!=last]+[last])
    return dict(storage=bytes(storage),offsets=offsets,playlist=[offsets[s] for s in pieces],
                unique=unique,cost=len(storage)+len(pieces))


def pack(stream,source_chunks=(),candidate_limit=96,max_entry_offset=None):
    if max_entry_offset is not None and (type(max_entry_offset) is not int or max_entry_offset<0):
        raise ValueError('Entry offset limit must be a nonnegative integer')
    stream=bytes(stream);aa=atoms(stream)
    vocabulary={a:i for i,a in enumerate(dict.fromkeys(aa))}
    seq=tuple(vocabulary[a] for a in aa);n=len(seq)
    weights=[len(a) for a in aa]
    locations=defaultdict(list)
    for length in range(1,min(64,n)+1):
        for i in range(n-length+1):locations[seq[i:i+length]].append(i)
    raw={};rank=[]
    for key,where in locations.items():
        if len(where)<2:continue
        end=-1;count=0
        for start in where:
            if start>=end:count+=1;end=start+len(key)
        word=b''.join(aa[where[0]:where[0]+len(key)])
        gain=count*(len(word)-1)-len(word)-1
        if gain>0:raw[key]=word;rank.append((-gain,-len(word),word,key))
    rank.sort();candidates=[row[-1] for row in rank[:candidate_limit]]
    # Musical-grid seeds avoid getting trapped in a poor greedy dictionary.
    # No user section annotations are required: durations reveal bar boundaries.
    bars=[];buffer=bytearray();units=0
    for atom in aa:
        if atom[-1]&7==7:raise ValueError('Reserved duration code 7')
        buffer.extend(atom);units+=(1,2,3,4,6,8,16)[atom[-1]&7]
        if units%16==0:bars.append(bytes(buffer));buffer.clear()
    if buffer:bars.append(bytes(buffer))
    seed_chunks=[list(source_chunks) if source_chunks else [stream]]
    for width in range(1,min(16,len(bars))+1):
        for shift in range(width):
            chunks=([b''.join(bars[:shift])] if shift else [])
            chunks += [b''.join(bars[i:i+width]) for i in range(shift,len(bars),width)]
            seed_chunks.append(chunks)
    seed_chunks.sort(key=lambda chunks:layout(chunks)['cost'])
    seed_chunks=seed_chunks[:4]
    manual=[]
    for chunks in seed_chunks:
        keys=[]
        for chunk in chunks:
            key=tuple(vocabulary[a] for a in atoms(chunk))
            if key and key not in keys:
                keys.append(key);raw[key]=bytes(chunk)
                if key not in locations:
                    locations[key]=[i for i in range(n-len(key)+1) if seq[i:i+len(key)]==key]
        manual.append(set(keys))

    def parse(dictionary):
        matches=[[] for _ in range(n)]
        for key in sorted(dictionary):
            for i in locations[key]:matches[i].append(key)
        normal=[0]*(n+1);literal=[0]*(n+1);choices=[None]*n;lchoices=[None]*n
        for i in range(n-1,-1,-1):
            normal[i]=2+weights[i]+literal[i+1]
            literal[i]=weights[i]+literal[i+1]
            for key in matches[i]:
                cost=1+normal[i+len(key)]
                if cost<normal[i]:normal[i]=cost;choices[i]=key
                if cost<literal[i]:literal[i]=cost;lchoices[i]=key
        pieces=[];buffer=bytearray();used=set();counts=Counter();i=0;inside=False
        while i<n:
            key=lchoices[i] if inside else choices[i]
            if key is None:buffer.extend(aa[i]);i+=1;inside=True
            else:
                if buffer:pieces.append(bytes(buffer));buffer.clear()
                pieces.append(raw[key]);used.add(key);counts[key]+=1;i+=len(key);inside=False
        if buffer:pieces.append(bytes(buffer))
        result=layout(pieces);result['dictionary']=used;result['counts']=counts
        assert b''.join(pieces)==stream
        return result

    def fitness(result):
        base=(result['cost'],len(result['storage']),result['storage'])
        if max_entry_offset is None:return base
        return (max(0,max(result['offsets'].values(),default=0)-max_entry_offset),)+base
    trials=0
    def improve(seed):
        nonlocal trials
        current=parse(seed)
        for _ in range(20):
            best=current;chosen=current['dictionary']
            removals=[chosen-{key} for key in sorted(chosen)]
            removals.append({key for key in chosen if current['counts'][key]>1})
            for reduced in removals:
                trial=parse(reduced);trials+=1
                if fitness(trial)<fitness(best):best=trial
            for key in candidates:
                if key in chosen:continue
                trial=parse(chosen|{key});trials+=1
                if fitness(trial)<fitness(best):best=trial
            if fitness(best)>=fitness(current):break
            current=best
        return current

    baseline=layout([bytes(c) for c in source_chunks]) if source_chunks else layout([stream])
    best=min([baseline,*[layout(chunks) for chunks in seed_chunks],improve(set()),*[improve(seed) for seed in manual]],
             key=fitness)
    names={word:f'packed_{i:03d}' for i,word in enumerate(best['unique'])}
    # Recover words for each emitted reference, including shared suffixes.
    by_offset={best['offsets'][word]:names[word] for word in best['unique']}
    playlist=[by_offset[offset] for offset in best['playlist']]
    expanded=b''.join(best['storage'][offset:best['storage'].index(255,offset)] for offset in best['playlist'])
    assert expanded==stream,'Packed output changed the music'
    return dict(storage=best['storage'],offsets={names[w]:p for w,p in best['offsets'].items()},playlist=playlist,
        sections={names[w]:list(w)+[255] for w in best['unique']},report=dict(
            method='Repeated command phrases; dynamic-programming parsing; suffix sharing; deterministic dictionary search',
            globallyMinimal=False,candidateLimit=candidate_limit,candidateCount=len(candidates),dictionaryTrials=trials,
            originalCommandBytes=len(stream),originalStreamSha256=hashlib.sha256(stream).hexdigest(),
            sourceLayoutBytes=baseline['cost'],packedEventBytes=len(best['storage']),playlistBytes=len(playlist),
            packedBytes=best['cost'],savedAgainstSourceLayoutBytes=baseline['cost']-best['cost'],
            storedSections=sum(x==255 for x in best['storage']),referencedSections=len(best['unique']),
            verifiedLossless=True))


if __name__=='__main__':
    import argparse
    import importlib.util
    from pathlib import Path
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('score');ap.add_argument('-o','--output',required=True)
    args=ap.parse_args()
    spec=importlib.util.spec_from_file_location('score',Path(__file__).with_name('score-format.py'))
    compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
    text,meta=compiler.to_inc(json.loads(Path(args.score).read_text(encoding='utf-8')))
    Path(args.output).write_text(text,encoding='utf-8',newline='\n')
    print(json.dumps(meta['compression'],indent=2))
