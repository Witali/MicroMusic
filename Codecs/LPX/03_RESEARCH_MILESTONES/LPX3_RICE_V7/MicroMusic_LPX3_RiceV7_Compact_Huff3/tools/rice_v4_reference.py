#!/usr/bin/env python3
"""LPX3 L3AV v4 offline compressor. All LPC/residual values lossless from L3AV v1.

Fixed 16-entry normal mode map retained from v3; id=15 is extended with two
bits (b6 Rice k4 / b6 zero±1 / b6 zero±1±2 / b4 zero±1±2).
For 10-bit LSF frames, `0` repeats coefficients; `1` followed by the old
(nonrepeat) mode family, including a new split 3-bit high / 5-bit low delta.
No runtime symbol statistics or SRAM dictionary; expensive mode selection is
performed solely by this host-side encoder.
"""
from pathlib import Path
import sys,struct,json,collections,argparse
from l3av_parse import unpack
from rice_v3 import BitReader,BitWriter,mapped,MODES,delta_string,write_code,read_code

# Extended submode under regular 4-bit index 15
# ext 0 = old 6-bit k4; 1 = b6 P1; 2 = b6 P2; 3 = b4 P2
EXTRAS=((6,4,'rice'),(6,0,'p1'),(6,0,'p2'),(4,0,'p2'))
SCALE_K=4
SCALE_LIMIT=6


def write_scale(w,previous,value):
    delta=value-previous
    z=mapped(delta)
    quotient=z>>SCALE_K
    if quotient<SCALE_LIMIT:
        for _ in range(quotient):w.put(0,1)
        w.put(1,1)
        w.put(z&((1<<SCALE_K)-1),SCALE_K)
        return 'rice'
    for _ in range(SCALE_LIMIT):w.put(0,1)
    w.put(value,8)
    return 'escape'


def read_scale(rd,previous):
    quotient=0
    while quotient<SCALE_LIMIT and rd.get(1)==0:quotient+=1
    if quotient==SCALE_LIMIT:return rd.get(8)
    z=(quotient<<SCALE_K)|rd.get(SCALE_K)
    delta=zigzag_back(z)
    result=previous+delta
    if not 0<=result<256:raise ValueError('invalid scale delta')
    return result


def zigzag_back(z):
    return (z>>1) if not(z&1) else -((z+1)>>1)


def pref_bits(v,b,style):
    if v==0:return 1
    if abs(v)==1:return 3
    if style=='p2' and abs(v)==2:return 4
    return b+(2 if style=='p1' else 3)


def best_mode_v4(blk):
    b=blk['bits'];data=blk['q'];z=[mapped(v) for v in data]
    options=[]
    for idx,(mb,k) in enumerate(MODES):
        if mb!=b:continue
        if not k:cost=b*len(data)
        else:
            highs=[v>>k for v in z]
            if max(highs,default=0)>8:continue
            cost=sum(x+1+k for x in highs)
        extra=2 if idx==15 else 0
        options.append((cost+extra,idx,0,'rice' if k else 'raw',k))
    for ext,(mb,k,style) in enumerate(EXTRAS[1:],start=1):
        if b==mb:
            cost=sum(pref_bits(v,b,style) for v in data)
            options.append((cost+2,15,ext,style,0))
    return min(options)


def putprefix(writer,x,b,style):
    if x==0:writer.put(0,1);return
    writer.put(1,1)
    if abs(x)==1:
        writer.put(0,1);writer.put(int(x<0),1);return
    writer.put(1,1)
    if style=='p2':
        if abs(x)==2:
            writer.put(0,1);writer.put(int(x<0),1);return
        writer.put(1,1)
    writer.put(x+(1<<(b-1)),b)


def getprefix(reader,b,style):
    if reader.get(1)==0:return 0
    if reader.get(1)==0:return -1 if reader.get(1) else 1
    if style=='p2':
        if reader.get(1)==0:return -2 if reader.get(1) else 2
    return reader.get(b)-(1<<(b-1))


def plane_cost(d):
    vals=[v-256 if v>=128 else v for v in d]
    return sum(mapped(v>>5)+1+(1 if not (v&31) else 6) for v in vals)


def putplane(w,byte):
    v=byte-256 if byte>=128 else byte
    high=mapped(v>>5)
    for _ in range(high):w.put(0,1)
    w.put(1,1)
    lo=v&31
    if lo==0:w.put(0,1)
    else:w.put(1,1);w.put(lo,5)


def getplane(rd):
    high=0
    while rd.get(1)==0:
        high+=1
        if high>7:raise ValueError('invalid LPC plane unary')
    upper=zigzag_back(high)
    lo=rd.get(5) if rd.get(1) else 0
    return ((upper<<5)+lo)&255


def encode_v4(doc):
    res=bytearray(doc['raw'][:20]);res[4]=4
    if res[5]&~3:raise ValueError('unsupported format flags')
    coeff10=bool(res[5]&1)
    if len(doc['frames'])*2 < len(doc['blocks']):raise ValueError('bad block layout')
    lastscale=0;counts=collections.Counter();w=BitWriter()
    for i,fb in enumerate(doc['frames']):
        tag=fb[0];payload=fb[1:]
        if coeff10:
            if tag==0:
                w.put(0,1);counts['repeat_frames']+=1
            elif tag==5:
                w.put(1,1);w.put(0,2)
                for v in payload:w.put(v,8)
            elif tag==7:
                w.put(1,1);w.put(3,2);w.put(0,1)
                for v in payload:w.put(v,8)
            elif tag==6:
                raw=80
                vlc=sum(len(delta_string(v-256 if v>=128 else v)) for v in payload)
                plane=plane_cost(payload)
                # raw & legacy VLC have 3-bit tag; plane has a 4-bit tag.
                kind=min((raw+3,'raw'),(vlc+3,'vlc'),(plane+4,'plane'))[1]
                if kind=='raw':
                    w.put(1,1);w.put(1,2)
                    for v in payload:w.put(v,8)
                elif kind=='vlc':
                    w.put(1,1);w.put(2,2)
                    for v in payload:write_code(w,v-256 if v>=128 else v)
                else:
                    w.put(1,1);w.put(3,2);w.put(1,1)
                    for v in payload:putplane(w,v)
                counts['frame_'+kind]+=1
            else:raise ValueError('unsupported 10-bit frame tag '+str(tag))
        else:
            # LSF8 and signed-LPC8 keep existing 3-bit tag format.
            if tag==6:
                vals=[v-256 if v>=128 else v for v in payload]
                vlc=sum(len(delta_string(v)) for v in vals)
                if vlc<80 and (res[5]&2):
                    # The existing v3 decoder supports tag4 for 10-bit only.
                    raise ValueError('8-bit tag6 not supported by existing core')
            w.put(tag,3)
            for v in payload:w.put(v,8)
        for blk in doc['blocks'][i*2:i*2+2]:
            _,idx,ext,style,k=best_mode_v4(blk)
            b=blk['bits'];vals=blk['q']
            w.put(idx,4)
            if idx==15:w.put(ext,2)
            counts[f'mode_{b}_{style}{k if style=="rice" else ""}']+=1
            counts['scale_'+write_scale(w,lastscale,blk['scale'])]+=1
            lastscale=blk['scale']
            if not b:pass
            elif style=='raw':
                for v in vals:w.put(v+(1<<(b-1)),b)
            elif style=='rice':
                for v in vals:
                    zz=mapped(v)
                    for _ in range(zz>>k):w.put(0,1)
                    w.put(1,1);w.put(zz&((1<<k)-1),k)
            else:
                for v in vals:putprefix(w,v,b,style)
    bitcount=w.total;w.aligned();res.extend(w.get())
    counts.update(frames=len(doc['frames']),blocks=len(doc['blocks']),samples=doc['sampleCount'],
       bytes_v1=len(doc['raw']),bytes_v4=len(res),total_bits=bitcount,
       saved_from_v1=len(doc['raw'])-len(res))
    return bytes(res),dict(counts)


def decode_v4(data):
    if len(data)<20:raise ValueError('short L3AV header')
    magic,version,flags,rate,n,pre,bright,fr,blk=struct.unpack_from('<4sBBHIHHHH',data)
    if magic!=b'L3AV' or version!=4 or flags&~3 or rate!=8000 or fr!=160 or blk!=80 or not n:
        raise ValueError('invalid L3AV v4 header')
    rd=BitReader(data,20);frames=[];blocks=[];oldscale=0;position=0
    while position<n:
        if flags&1:
            if rd.get(1)==0:tag=0
            else:
                family=rd.get(2)
                tag=(5,6,4,None)[family]
                if tag is None:tag=7 if rd.get(1)==0 else 1
        else:tag=rd.get(3)
        num={0:0,1:10+int(not(flags&2)),2:5,3:10,5:13+int(not(flags&2)),6:10,7:5}
        if tag==4:
            if not(flags&1):raise ValueError('invalid 8-bit delta tag')
            payload=[read_code(rd)&255 for _ in range(10)]
            fb=bytes([6]+payload)
        elif tag==1 and flags&1:
            payload=[getplane(rd) for _ in range(10)]
            fb=bytes([6]+payload)
        else:
            if tag not in num:raise ValueError('invalid frame tag')
            fb=bytes([tag]+[rd.get(8) for _ in range(num[tag])])
        frames.append(fb)
        for _ in range(2):
            if position>=n:break
            idx=rd.get(4)
            if idx==15:
                extra=rd.get(2)
                b,k,style=EXTRAS[extra]
            else:
                b,k=MODES[idx];style='rice' if k else 'raw'
            scale=read_scale(rd,oldscale);oldscale=scale
            count=min(80,n-position)
            if not b:q=[0]*count
            elif style=='raw':q=[rd.get(b)-(1<<(b-1)) for _ in range(count)]
            elif style=='rice':
                q=[]
                for _ in range(count):
                    hi=0
                    while rd.get(1)==0:
                        hi+=1
                        if hi>8:raise ValueError('invalid Rice unary')
                    z=(hi<<k)|rd.get(k)
                    if z>=1<<b:raise ValueError('invalid Rice magnitude')
                    q.append(zigzag_back(z))
            else:
                q=[getprefix(rd,b,style) for _ in range(count)]
            blocks.append({'bits':b,'scale':scale,'q':q})
            position+=count
    if rd.o!=len(data):raise ValueError('trailing stream data')
    return frames,blocks


def verify_eq(doc,new):
    f,b=decode_v4(new)
    assert f==doc['frames'],('frames differ',f[:2],doc['frames'][:2])
    assert [(v['bits'],v['scale'],v['q']) for v in b]==[(v['bits'],v['scale'],v['q']) for v in doc['blocks']]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');p.add_argument('--report');args=p.parse_args()
    document=unpack(Path(args.source).read_bytes());data,stats=encode_v4(document)
    verify_eq(document,data);Path(args.target).write_bytes(data)
    if args.report:Path(args.report).write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(stats,ensure_ascii=False,indent=2))
