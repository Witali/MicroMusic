#!/usr/bin/env python3
"""L3AV v7 mode-repeat + fixed Huff3: compact, *lossless* repacking of quantized 10-bit LSF + VBR residual.

Design goals: 16 MHz ATmega328P, smallest *combined* ROM footprint
(decoder+compressed stream); bounded Rice unary, no dictionary, no prefix
exceptions, no 8-bit LPC, no legacy modes. Heavy decisions happen offline.
"""
import sys,struct,json,argparse,collections
from pathlib import Path
from l3av_parse import unpack
from rice_v3 import BitWriter,BitReader,mapped,MODES as OLD_MODES
MODES=OLD_MODES[:15]+((3,-1),)
HUFF3={-1:'00', 2:'010', -2:'011', 0:'10', 3:'1100', -4:'11010', -3:'11011', 1:'111'}
HUFF3_DECODE={v:k for k,v in HUFF3.items()}

from rice_v4_reference import write_scale,read_scale,plane_cost,putplane,getplane


def best_block(blk):
    b=blk['bits'];q=blk['q'];z=[mapped(v) for v in q]
    eligible=[]
    for idx,(mb,k) in enumerate(MODES):
        if mb!=b:continue
        if k==-1:
            cost=sum(len(HUFF3[v]) for v in q)
        elif not k:cost=len(q)*b
        else:
            if max((v>>k for v in z),default=0)>8:continue
            cost=sum((v>>k)+1+k for v in z)
        eligible.append((cost,idx,k))
    if not eligible:raise ValueError('no valid block mode')
    return min(eligible)


def absolute_lsf10(payload):
    if len(payload)!=13:raise ValueError('10-bit absolute LSF requires 13 bytes')
    v=int.from_bytes(payload,'little')
    return [(v>>(i*10))&1023 for i in range(10)]


def encode_v7(doc):
    if doc['raw'][:4]!=b'L3AV' or doc['raw'][5]!=3:raise ValueError('v7 requires 10-bit LSF source flags 3')
    out=bytearray(doc['raw'][:20]);out[4]=7
    w=BitWriter();stats=collections.Counter();lastscale=0;lastMode=0
    for i,frame in enumerate(doc['frames']):
        tag=frame[0];payload=frame[1:]
        if tag==0:
            w.put(0,1);stats['frame_repeat']+=1
        elif tag==5:
            w.put(1,1);w.put(0,1)
            for v in absolute_lsf10(payload):w.put(v&255,8);w.put(v>>8,2)
            stats['frame_full']+=1
        elif tag==6:
            w.put(1,1);w.put(1,1)
            if len(payload)!=10:raise ValueError('signed 10-coefficient delta expected')
            bits_plane=plane_cost(payload);raw=80
            use_raw = raw <= bits_plane
            w.put(int(use_raw),1)
            if use_raw:
                for v in payload:w.put(v,8)
                stats['delta_raw']+=1
            else:
                for v in payload:putplane(w,v)
                stats['delta_plane']+=1
        else:
            raise ValueError('v5 supports only repeat, full and LPC delta frames; input tag '+str(tag))
        for block in doc['blocks'][2*i:2*i+2]:
            _,idx,k=best_block(block)
            b=block['bits']
            if idx==lastMode:
                w.put(0,1);stats['mode_repeat']+=1
            else:
                w.put(1,1);w.put(idx,4);stats['mode_explicit']+=1;lastMode=idx
            stats[f'block_{b}_{k}']+=1
            stats['scale_'+write_scale(w,lastscale,block['scale'])]+=1
            lastscale=block['scale']
            if b==0:continue
            if k==-1:
                for v in block['q']:
                    for bit in HUFF3[v]:w.put(int(bit),1)
            elif k==0:
                for v in block['q']:w.put(v+(1<<(b-1)),b)
            else:
                for v in block['q']:
                    z=mapped(v)
                    for _ in range(z>>k):w.put(0,1)
                    w.put(1,1);w.put(z&((1<<k)-1),k)
    bitcount=w.total;w.aligned();out+=w.get()
    stats.update(samples=doc['sampleCount'],frames=len(doc['frames']),blocks=len(doc['blocks']),size_v1=len(doc['raw']),size_v5=len(out),total_bits=bitcount)
    return bytes(out),dict(stats)


def decode_v7(data):
    if len(data)<20:raise ValueError('short header')
    magic,ver,flags,rate,n,pre,bright,f,b=struct.unpack_from('<4sBBHIHHHH',data)
    if magic!=b'L3AV' or ver!=7 or flags!=3 or rate!=8000 or n==0 or f!=160 or b!=80:
        raise ValueError('unsupported v7 file header')
    rd=BitReader(data,20);pos=0;frames=[];blocks=[];oldscale=0;lastMode=0
    while pos<n:
        if rd.get(1)==0:fb=b'\x00'
        elif rd.get(1)==0:
            coeffs=[rd.get(8)|(rd.get(2)<<8) for _ in range(10)]
            acc=sum(v << (10*i) for i,v in enumerate(coeffs))
            fb=b'\x05'+acc.to_bytes(13,'little')
        else:
            raw=rd.get(1)
            delta=[rd.get(8) for _ in range(10)] if raw else [getplane(rd) for _ in range(10)]
            fb=b'\x06'+bytes(delta)
        frames.append(fb)
        for _ in range(2):
            if pos>=n:break
            if rd.get(1):lastMode=rd.get(4)
            bits,k=MODES[lastMode]
            scale=read_scale(rd,oldscale);oldscale=scale
            cnt=min(80,n-pos)
            q=[]
            for _ in range(cnt):
                if bits==0:v=0
                elif k==-1:
                    prefix=''
                    while prefix not in HUFF3_DECODE:
                        prefix+=str(rd.get(1))
                        if len(prefix)>5:raise ValueError('bad Huff3 code')
                    v=HUFF3_DECODE[prefix]
                elif k==0:v=rd.get(bits)-(1<<(bits-1))
                else:
                    hi=0
                    while rd.get(1)==0:
                        hi+=1
                        if hi>8:raise ValueError('invalid Rice unary')
                    z=(hi<<k)|rd.get(k)
                    if z >= 1<<bits:raise ValueError('Rice code out of range')
                    v=(z>>1) if not z&1 else -((z+1)>>1)
                q.append(v)
            blocks.append({'bits':bits,'scale':scale,'q':q})
            pos+=cnt
    if rd.o!=len(data):raise ValueError('trailing data')
    return frames,blocks


def verify_eq(doc, encoded):
    frames,blocks=decode_v7(encoded)
    # Each original 10-bit absolute frame has 4 byte-alignment padding bits.
    for f,g in zip(frames,doc['frames']):
        if f[0]==5 and g[0]==5:
            assert absolute_lsf10(f[1:])==absolute_lsf10(g[1:])
        else: assert f==g,('frame mismatch',f,g)
    assert len(frames)==len(doc['frames'])
    assert [(x['bits'],x['scale'],x['q']) for x in blocks]==[(x['bits'],x['scale'],x['q']) for x in doc['blocks']]


def cli():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('dest');ap.add_argument('--report');args=ap.parse_args()
    doc=unpack(Path(args.source).read_bytes());b,s=encode_v7(doc);verify_eq(doc,b);Path(args.dest).write_bytes(b)
    if args.report:Path(args.report).write_text(json.dumps(s,indent=2,ensure_ascii=False))
    print(json.dumps(s,ensure_ascii=False))
if __name__=='__main__':cli()
