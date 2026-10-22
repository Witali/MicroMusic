#!/usr/bin/env python3
"""Offline-selected lossless excitation-pair dictionary, L3AV v2.

Stream retains frame coefficients, scale, number of samples, and signed residuals
unchanged. Decoder never searches for patterns or chooses victims. Pair table is
updated only through explicit in-band commands preplanned by this encoder.
No training/source audio required to run this transcode. It is lossless w.r.t.
L3AV v1 quantized excitation, not w.r.t. original WAV.
"""
import sys, math, struct, argparse, collections, json
from pathlib import Path
from l3av_parse import unpack

CAPS=(64,128,256,512)

class BitWriter:
    def __init__(self):self.bits=[]
    def put(self, v, n):
        assert 0<=v<(1<<n)
        for i in range(n):self.bits.append((v>>i)&1)
    def bytes(self):
        a=bytearray((len(self.bits)+7)//8)
        for i,b in enumerate(self.bits):a[i>>3]|=b<<(i&7)
        return bytes(a)

class BitReader:
    def __init__(self,d):self.data=d;self.bitpos=0
    def get(self,n):
        x=0
        for i in range(n):
            if self.bitpos>>3>=len(self.data):raise ValueError('EOF in bitstream')
            x|=((self.data[self.bitpos>>3]>>(self.bitpos&7))&1)<<i;self.bitpos+=1
        return x

# K=2 signed 8-bit residual values in SRAM. Slots 0..15 are hot tier.
HOT=16

def pair_blocks(doc):
 return [[tuple(bl['q'][i:i+2]) for i in range(0,len(bl['q']),2)] for bl in doc['blocks']]

def gain_ref(bits,index,indexbits,tiered):
    # Cost of raw pair: 1 + 2*bits, one control bit. Diff is <= 0 if no gain.
    if tiered:
        refbits=(2+4) if index<HOT else 3+indexbits
    else:refbits=2+indexbits
    return (1+2*bits)-refbits

def gain_for_tier(bits,hot,indexbits,tiered):
    if tiered:
        rb=6 if hot else (3+indexbits)
    else:rb=2+indexbits
    return max(0,1+2*bits-rb)

def choose_window(doc, pairs, start, stop, slots, indexbits, tiered, state):
    occurrences=collections.defaultdict(list)
    for j in range(start,stop):
        m=doc['blocks'][j]['bits']
        for p in pairs[j]:
            if len(p)==2:occurrences[p].append(m)
    scored=[]
    hot_limit=HOT if tiered else slots
    for p,mb in occurrences.items():
        hot=0;cold=0
        was_hot=p in state[:hot_limit];was_cold=p in state[hot_limit:]
        for t,m in enumerate(mb):
            if t or was_hot:hot+=gain_for_tier(m,True,indexbits,tiered)
            if t or was_cold:cold+=gain_for_tier(m,False,indexbits,tiered)
        if not was_hot: hot-=indexbits+(3 if tiered else 2)
        if not was_cold: cold-=indexbits+(3 if tiered else 2)
        scored.append((p,hot,cold))
    # Prioritize saving the most expensive matches in hot table.
    hot=sorted(scored,key=lambda z:(z[1]-z[2],z[1]),reverse=True)
    hot_target=[p for p,gh,gc in hot if gh>0][:hot_limit]
    if not tiered:return hot_target, []
    cold=sorted(scored,key=lambda z:z[2],reverse=True)
    cold_target=[p for p,gh,gc in cold if gc>0 and p not in hot_target][:slots-hot_limit]
    return hot_target,cold_target

def make_target_map(existing, desired, start_slot, end_slot):
    assigned={};occupied=set()
    # Reuse slot positions within the same tier whenever possible.
    for p in desired:
        for ix in range(start_slot,end_slot):
            if existing[ix]==p and ix not in occupied:
                assigned[p]=ix;occupied.add(ix);break
    spare=iter(ix for ix in range(start_slot,end_slot) if ix not in occupied)
    for p in desired:
        if p not in assigned:assigned[p]=next(spare)
    return assigned

def rice_candidate(block):
    b=block['bits'];q=block['q'];rawlen=len(block['bytes'])-2
    best=None
    for k in range(1,b):
        bw=BitWriter()
        for v in q:
            zz=(2*v if v>=0 else -2*v-1)
            for _ in range(zz>>k):bw.put(0,1)
            bw.put(1,1);bw.put(zz & ((1<<k)-1),k)
        packed=bw.bytes()
        if len(packed)<rawlen and (best is None or len(packed)<len(best[1])):
            best=(k,packed)
    if best is None:return None
    k,payload=best
    return bytes([0x80 | (k<<4) |b,block['scale']])+payload

def compress(doc, cap=128, window=12, tiered=True, fallback=True, rice=True):
    if cap not in CAPS:raise ValueError('cap must be 64/128/256/512')
    pairs=pair_blocks(doc);slots=cap//2;ib=slots.bit_length()-1
    srcblocks=doc['blocks']
    state=[None]*slots
    all_payload=[];outstats=collections.Counter();dmarkers=[]
    hotmap={};coldmap={}
    for j,bl in enumerate(srcblocks):
        if j%window==0:
            h,c=choose_window(doc,pairs,j,min(j+window,len(srcblocks)),slots,ib,tiered,state)
            hot_limit=HOT if tiered else slots
            hotmap=make_target_map(state,h,0,hot_limit)
            coldmap=make_target_map(state,c,hot_limit,slots) if tiered else {}
        mapping={**hotmap,**coldmap}
        bit=bl['bits'];n=len(bl['q'])
        bw=BitWriter();updated=state.copy();stats=collections.Counter()
        for p in pairs[j]:
            if len(p)==1:
                bw.put(0,1);bw.put(p[0]+(1<<(bit-1)),bit);stats['single']+=1
                continue
            ixexisting=next((ix for ix,v in enumerate(updated) if v==p),None)
            # Choose the lowest-cost valid index when duplicates exist.
            all_existing=[ix for ix,v in enumerate(updated) if v==p]
            ixexisting=min(all_existing,key=lambda ix:(2+4 if tiered and ix<HOT else 3+ib if tiered else 2+ib)) if all_existing else None
            benefit=gain_ref(bit,ixexisting,ib,tiered) if ixexisting is not None else -999
            if ixexisting is not None and benefit>0:
                if tiered:
                    if ixexisting<HOT:bw.put(1,1);bw.put(0,1);bw.put(ixexisting,4)
                    else:bw.put(1,1);bw.put(1,1);bw.put(0,1);bw.put(ixexisting,ib)
                else:bw.put(1,1);bw.put(0,1);bw.put(ixexisting,ib)
                stats['hit']+=1;stats['hit_hot' if tiered and ixexisting<HOT else 'hit_cold']+=1
                continue
            wanted=mapping.get(p)
            # Replace at first use, if it is in the precomputed table. Updates include raw pair.
            if wanted is not None and updated[wanted]!=p and ixexisting is None:
                if tiered:bw.put(1,1);bw.put(1,1);bw.put(1,1)
                else:bw.put(1,1);bw.put(1,1)
                bw.put(wanted,ib)
                for a in p:bw.put(a+(1<<(bit-1)),bit)
                updated[wanted]=p;stats['update']+=1
            else:
                bw.put(0,1)
                for a in p:bw.put(a+(1<<(bit-1)),bit)
                stats['literal']+=1
        payload=bw.bytes();raw=bl['bytes'][2:]
        # Base format has no token overhead, available fallback mode per block.
        ric=(rice_candidate(bl) if rice else None)
        baseline=bl['bytes'];baseline_type='rawblock'
        if ric is not None and len(ric)<len(baseline):baseline=ric;baseline_type='riceblock'
        if fallback and len(payload)>=len(baseline)-2:
            stats=collections.Counter({baseline_type:1})
            all_payload.append(baseline);dmarkers.append(0)
        else:
            stats['dictblock']=1
            state=updated
            all_payload.append(bytes([bl['bits']|0x40,bl['scale']])+payload);dmarkers.append(1)
        outstats.update(stats)
    # Rewrite only header version and 2-bit cap field, coefficients remain verbatim.
    data=bytearray(doc['raw'][:20]);data[4]=2;data[5]=(data[5]&3)|((CAPS.index(cap)&3)<<4)|(4 if tiered else 0)
    for j,coeff in enumerate(doc['frames']):
        data.extend(coeff);data.extend(all_payload[j*2]);
        if j*2+1<len(all_payload):data.extend(all_payload[j*2+1])
    result={'bytes':len(data),'original_bytes':len(doc['raw']),'saved_bytes':len(doc['raw'])-len(data),
            'ratio':round(len(data)/len(doc['raw']),4),'cap':cap,'window':window,'tiered':tiered,
            'fallback':fallback,'blocks':len(srcblocks),'dict_blocks':outstats['dictblock'],
            'updates':outstats['update'],'hits':outstats['hit'],'hot_hits':outstats['hit_hot'],
            'cold_hits':outstats['hit_cold'],'raw_blocks':outstats['rawblock'],'rice_blocks':outstats['riceblock']}
    return bytes(data), result

def decompress(data):
    head=data[:20];magic,ver,fl,rate,n,pre,bright,fs,bs=struct.unpack('<4sBBHIHHHH',head)
    assert magic==b'L3AV' and ver==2 and (fl&3) in (2,3)
    cap=CAPS[(fl>>4)&3];slots=cap//2;indexbits=slots.bit_length()-1;tiered=bool(fl&4)
    state=[None]*slots;o=20;frames=[];bl=[];samples=0
    while samples<n:
        start=o;tag=data[o];o+=1
        ncoef={0:0,1:10+(not(fl&2)),2:5,3:10,5:13+(not(fl&2)),6:10,7:5}[tag]
        o+=ncoef;frames.append(data[start:o]);assert o<=len(data)
        for _ in range(2):
            if samples>=n:break
            m,scale=data[o:o+2];o+=2
            dflag=m&0x40;rflag=m&0x80;b=(m&7 if rflag else m&~0x40);cnt=min(80,n-samples)
            if rflag:
                k=(m>>4)&7
                assert 1<=k<b<=6
                reader=BitReader(data[o:]);q=[]
                for __ in range(cnt):
                    quotient=0
                    while not reader.get(1):
                        quotient+=1
                        assert quotient<=((1<<b)>>k)
                    zz=(quotient<<k)|reader.get(k)
                    v=(zz>>1) if (zz&1)==0 else -((zz+1)>>1)
                    assert -(1<<(b-1))<=v<(1<<(b-1))
                    q.append(v)
                o+=(reader.bitpos+7)//8
            elif dflag:
                assert b in range(2,7)
                reader=BitReader(data[o:]);q=[]
                while len(q)<cnt:
                    t=reader.get(1)
                    if t==0:
                        pair=[reader.get(b)-(1<<(b-1))]
                        if len(q)+1<cnt:pair.append(reader.get(b)-(1<<(b-1)))
                    else:
                        t=reader.get(1)
                        if t==0:
                            idx=reader.get(4 if tiered else indexbits); assert idx<(16 if tiered else slots) and state[idx] is not None;pair=state[idx]
                        else:
                            t=reader.get(1) if tiered else 1
                            if t==0:
                                idx=reader.get(indexbits); assert 16<=idx<slots and state[idx] is not None;pair=state[idx]
                            else:
                                idx=reader.get(indexbits);assert idx<slots
                                pair=[reader.get(b)-(1<<(b-1)),reader.get(b)-(1<<(b-1))]
                                state[idx]=tuple(pair)
                    assert len(q)+len(pair)<=cnt
                    q.extend(pair)
                o+=(reader.bitpos+7)//8
            else:
                assert b in range(2,7)
                bytesNeeded=(cnt*b+7)//8
                rd=BitReader(data[o:o+bytesNeeded]);q=[rd.get(b)-(1<<(b-1)) for _ in range(cnt)]
                o+=bytesNeeded
            samples+=cnt;bl.append({'bits':b,'scale':scale,'q':q})
    assert o==len(data),(o,len(data))
    return frames,bl

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('infile');p.add_argument('outdir');p.add_argument('--windows',default='4,8,16,32,1000');args=p.parse_args()
    doc=unpack(Path(args.infile).read_bytes());out=Path(args.outdir);out.mkdir(exist_ok=True,parents=True)
    originalQs=[x['q'] for x in doc['blocks']];originalCo=doc['frames'];
    rows=[]
    for cap in CAPS:
      for window in [int(x) for x in args.windows.split(',')]:
       for tier in (False,True):
        for fallback in (False,True):
         packed,stats=compress(doc,cap,window,tier,fallback,True)
         fs,bs=decompress(packed)
         assert fs==originalCo and [(x['bits'],x['scale'],x['q']) for x in bs]==[(x['bits'],x['scale'],x['q']) for x in doc['blocks']]
         rows.append(stats)
         if cap==64 or stats['saved_bytes']>0:
          outf=out/(Path(args.infile).stem+f'_D{cap}_W{window}_T{int(tier)}_F{int(fallback)}.l3av')
          outf.write_bytes(packed)
    rows.sort(key=lambda s:s['bytes']);print(json.dumps(rows[:20],ensure_ascii=False,indent=2))
    (out/(Path(args.infile).stem+'_dictionary_benchmark.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
