#!/usr/bin/env python3
"""MicroMusic L3AV-v3 lossless repacker, fixed 16-mode nibble table.

Input: L3AV version-1 (quantized LPC plus residual) stream.
Output: L3AV version-3. Encodes EXACT SAME signed residuals and frame bytes.
Fixed mode table is shared by computer & tiny AVR decoder; no SRAM dictionary.
LSB-first bitstream, reset to byte boundary ONCE PER FRAME (160 samples),
never at the 80-sample block boundary. Bounded Rice unary quotient <=8.
"""
import sys,struct,json,collections,argparse
from pathlib import Path
from l3av_parse import unpack

# Each entry is (raw bit-width [0 or 2..6], Rice k [0 raw, 1..]).
# Generated statically by analysis of the available VBR audio samples and
# synthetic compatibility (all raw widths). Storage: 16 bytes PROGMEM.
MODES=((0,0),(2,0),(3,0),(4,0),(5,0),(6,0),
       (2,1),(3,1),(4,1),(4,2),(5,1),(5,2),(5,3),(6,2),(6,3),(6,4))
MODEBYTE=[b | (k<<3) for b,k in MODES]

class BitWriter:
    def __init__(self):self.out=bytearray();self.acc=0;self.n=0;self.total=0
    def put(self,x,nb):
        assert 0<=nb<=8 and 0<=x<(1<<nb)
        self.acc|=x<<self.n;self.n+=nb;self.total+=nb
        if self.n>=8:
            self.out.append(self.acc&255);self.acc>>=8;self.n-=8
    def aligned(self):
        if self.n:
            self.out.append(self.acc&255);self.acc=0;self.n=0
    def get(self):return bytes(self.out)

class BitReader:
    def __init__(self,d,start=0):self.data=d;self.o=start;self.acc=0;self.n=0
    def get(self,nb):
        while self.n<nb:
            if self.o>=len(self.data):raise ValueError('truncated frame data')
            self.acc|=self.data[self.o]<<self.n;self.o+=1;self.n+=8
        x=self.acc&((1<<nb)-1);self.acc>>=nb;self.n-=nb;return x
    def align(self):self.n=0;self.acc=0


def mapped(q):return 2*q if q>=0 else -2*q-1

def best_mode(bl):
    b=bl['bits'];q=bl['q'];cnt=len(q)
    choices=[]
    for ix,(mb,k) in enumerate(MODES):
        if mb!=b:continue
        if not k:cost=cnt*b;choices.append((cost,ix,0))
        else:
            zz=[mapped(x) for x in q]
            qs=[z>>k for z in zz]
            if max(qs,default=0)>8:continue
            cost=sum(v+1+k for v in qs)
            choices.append((cost,ix,k))
    if not choices:raise ValueError('no mode for b='+str(b))
    return min(choices)

def putscale(w,old,scale):
    if scale==old:w.put(0,1);return 'same'
    diff=scale-old
    if -8<=diff<=7:w.put(1,1);w.put(0,1);w.put(diff&15,4);return 'delta'
    w.put(1,1);w.put(1,1);w.put(scale,8);return 'absolute'

def readscale(rd,old):
    if rd.get(1)==0:return old
    if rd.get(1)==0:
        d=rd.get(4);d=d-16 if d&8 else d
        x=old+d
        if not 0<=x<256:raise ValueError('bad scale delta')
        return x
    return rd.get(8)

# Prefix-free, bounded VLC for the 10 LSF deltas of an updated frame.
# 1-bit zero; frequent multiples of 32; escape +8-bit literal. The AVR
# unpacks this ONCE PER 160 samples, never in the 8kHz excitation hot loop.
DELTA_CODES={0:'0',-32:'100',32:'101',-64:'1100',64:'1101',-96:'11100',96:'11101',-128:'11110'}
def delta_string(x):return DELTA_CODES.get(x,'11111' + ''.join(str((x>>i)&1) for i in range(8)))
def write_code(w,x):
    for ch in delta_string(x):w.put(int(ch),1)
def read_code(rd):
    if rd.get(1)==0:return 0
    if rd.get(1)==0:return -32 if rd.get(1)==0 else 32
    if rd.get(1)==0:return -64 if rd.get(1)==0 else 64
    if rd.get(1)==0:return -96 if rd.get(1)==0 else 96
    if rd.get(1)==0:return -128
    # escape is now a literal signed byte, LSB-first
    x=rd.get(8);return x-256 if x>=128 else x

def encode_v3(doc):
    res=bytearray(doc['raw'][:20]);res[4]=3
    if res[5] & ~3:raise ValueError('Unsupported flags')
    old=0;stats=collections.Counter();bit0=0
    w=BitWriter() # Single continuous bitstream for ALL frames and subblocks.
    for j,fb in enumerate(doc['frames']):
        # All original valid frame tags fit in three bits (0..7).
        if fb[0]==6:
            ds=[v-256 if v>=128 else v for v in fb[1:]]
            vlcbits=sum(len(delta_string(v)) for v in ds)
            if vlcbits<80:
                w.put(4,3) # tag 4 = compressed signed-byte deltas
                for delta in ds:write_code(w,delta)
                stats['vlc_frames']+=1
            else:
                w.put(6,3)
                for by in fb[1:]:w.put(by,8)
                stats['raw_delta_frames']+=1
        else:
            w.put(fb[0],3)
            for by in fb[1:]:w.put(by,8)
        for blk in doc['blocks'][j*2:j*2+2]:
            cost,ix,k=best_mode(blk);b=blk['bits'];q=blk['q']
            w.put(ix,4);stats[f'mode-{b}-{k}']+=1
            stats['scale-'+putscale(w,old,blk['scale'])]+=1;old=blk['scale']
            if k:
                for v in q:
                    z=mapped(v)
                    for _ in range(z>>k):w.put(0,1)
                    w.put(1,1);w.put(z & ((1<<k)-1),k)
            elif b:
                for v in q:w.put(v+(1<<(b-1)),b)
            stats['residual-bits']+=cost
    bit0=w.total;w.aligned();res.extend(w.get())
    stats.update(frames=len(doc['frames']),blocks=len(doc['blocks']),samples=doc['sampleCount'],stream_bits=bit0,
                 bytes_v1=len(doc['raw']),bytes_v3=len(res),saved=len(doc['raw'])-len(res))
    return bytes(res),dict(stats)

def decode_v3(data):
    h=struct.unpack_from('<4sBBHIHHHH',data)
    if len(data)<20 or h[0]!=b'L3AV' or h[1]!=3:raise ValueError('bad v3 header')
    if h[2]&~3:raise ValueError('bad flags')
    n=h[4];rd=BitReader(data,20);fr=[];bl=[];decoded=0;old=0
    while decoded<n:
        t=rd.get(3);ncoef={0:0,1:10+int(not(h[2]&2)),2:5,3:10,5:13+int(not(h[2]&2)),6:10,7:5}.get(t)
        if t==4:fr.append(bytes([6]+[(read_code(rd)&255) for _ in range(10)]))
        else:
            if ncoef is None:raise ValueError('bad frame')
            fr.append(bytes([t]+[rd.get(8) for _ in range(ncoef)]))
        for block_index in range(2):
            if decoded>=n:break
            idx=rd.get(4);b,k=MODES[idx];scale=readscale(rd,old);old=scale
            cnt=min(80,n-decoded)
            if b==0:q=[0]*cnt
            elif not k:q=[rd.get(b)-(1<<(b-1)) for _ in range(cnt)]
            else:
                q=[]
                for _ in range(cnt):
                    hi=0
                    while not rd.get(1):
                        hi+=1
                        if hi>8:raise ValueError('unary bound exceeded')
                    z=(hi<<k)|rd.get(k)
                    if z>=1<<b:raise ValueError('Rice out of range')
                    q.append(z//2 if z%2==0 else -(z+1)//2)
            bl.append({'bits':b,'scale':scale,'q':q})
            decoded+=cnt
    rd.align();o=rd.o
    if o!=len(data):raise ValueError(f'trailing bytes {len(data)-o}')
    return fr,bl

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('src');p.add_argument('dest');p.add_argument('--report');args=p.parse_args()
    d=unpack(Path(args.src).read_bytes());data,s=encode_v3(d)
    f,b=decode_v3(data)
    assert f==d['frames'] and [(x['bits'],x['scale'],x['q']) for x in b]==[(x['bits'],x['scale'],x['q']) for x in d['blocks']]
    Path(args.dest).write_bytes(data)
    if args.report:Path(args.report).write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(s,indent=2,ensure_ascii=False))
