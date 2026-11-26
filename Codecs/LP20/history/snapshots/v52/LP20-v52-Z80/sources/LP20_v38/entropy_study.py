"""Lossless host-only native token Huffman trial, independently reconstructing LPC context.
Header/4-bit code lengths included; Z80 unpacker not implemented.
"""
from pathlib import Path
import sys,json,heapq,struct,zlib,lzma
from collections import Counter
ROOT=Path(__file__).resolve().parent;B=ROOT.parent;sys.path.insert(0,str(B/'LP20_v37'))
from reuse_macros import np,f,decode_plan
from repack import step

def lengths(seq):
    counts=Counter(seq);out=np.zeros(256,np.uint8);h=[(n,k,[k]) for k,n in counts.items()];heapq.heapify(h);j=256
    while len(h)>1:
        a,_,x=heapq.heappop(h);b,_,y=heapq.heappop(h);out[x]+=1;out[y]+=1;heapq.heappush(h,(a+b,j,x+y));j+=1
    if len(h)==1 and len(h[0][2])==1:out[h[0][2][0]]=1
    return out

def codes(l):
    v=0;old=0;out={}
    for k in sorted(np.flatnonzero(l),key=lambda k:(l[k],k)):
        n=int(l[k]);v<<=n-old;assert v<1<<n;out[int(k)]=(v,n);v+=1;old=n
    return out

def context(n,amp,last):return 0 if n==1 else amp if n==2 else amp*(n//2)+min(n//2-1,last//(8 if n==4 else 4))

def run(clip):
    p=B/'LP20_v37/release'/clip/'Strict8';m=json.loads((p/'decoder.json').read_text());d=dict(np.load(p/'model.npz'));raw=(p/'decoder.bin').read_bytes()[m['used']-m['stream_bytes']-1:m['used']-1];rr=np.concatenate([d['records'],d['ext_records']]);ll=np.r_[d['lengths'],d['ext_lengths']];plan=d['plan'];th=int(d['threshold']);sm=int(d['shortmax']);tb=f.compact_tables(d['a']);pos=np.r_[0,np.cumsum(ll[plan])[:-1]];prev=np.r_[0,d['y'][:-1]][pos];amp=((prev>=th)|(prev< -th)).astype(int);j=0;words=[];maps={}
    for k,a in zip(plan,amp):
        end=j+1+(raw[j]>sm);word=raw[j:end];words.append(word);j=end
        key=(int(a),word);assert key not in maps or maps[key]==k;maps[key]=int(k)
    assert j==len(raw)
    # Map all short tokens directly from existing model; long tokens use ROM address map.
    out=[]
    for n in (1,2,4,8):
        cc=[context(n,int(a),int(last)) for a,last in zip(amp,np.r_[0,ll[plan][:-1]])];lens=np.array([lengths([w[0] for w,c in zip(words,cc) if c==i]) for i in range(n)]);assert lens.max()<=15
        ctab=[codes(l) for l in lens];bits=[]
        for w,c in zip(words,cc):
            v,b=ctab[c][w[0]];bits.extend((v>>j)&1 for j in range(b-1,-1,-1));
            if len(w)==2:bits.extend((w[1]>>j)&1 for j in range(7,-1,-1))
        hdr=struct.pack('<4sBI',b'LPH8',n,len(plan));flat=lens.ravel();blob=hdr+bytes((flat[::2]<<4)|flat[1::2])+np.packbits(bits).tobytes();(ROOT/clip/f'native-huff{n}.lph8').write_bytes(blob)
        magic,nt,nn=struct.unpack_from('<4sBI',blob);assert magic==b'LPH8' and nt==n;tab=np.frombuffer(blob[len(hdr):len(hdr)+n*128],np.uint8);l=np.empty(len(tab)*2,np.uint8);l[::2]=tab>>4;l[1::2]=tab&15;dt=[{v:k for k,v in codes(row).items()} for row in l.reshape(n,256)];bb=np.unpackbits(np.frombuffer(blob[len(hdr)+n*128:],np.uint8));i=0;hist=np.zeros(6,np.int16);last=0;decoded=bytearray();ix=[];yy=[]
        for _ in range(nn):
            a=int(hist[0]>=th or hist[0]<-th);ct=dt[context(n,a,last)];v=0
            for j in range(1,16):
                v=(v<<1)|int(bb[i]);i+=1
                if (v,j) in ct:k=ct[v,j];break
            else:raise ValueError('prefix')
            w=bytes([k]);
            if k>sm:
                v=0
                for z in range(8):v=(v<<1)|int(bb[i]);i+=1
                w+=bytes([v])
            decoded+=w;k=maps[a,w];ix.append(k);last=int(ll[k])
            for bank,r in rr[k,:last]:
                v,ov=step(hist,tb[bank],r,10);assert not ov;yy.append(v)
        assert bytes(decoded)==raw and np.array_equal(ix,plan) and np.array_equal(yy,d['y'])
        a=dict(clip=clip,contexts=n,original_bytes=len(raw),compressed_bytes=len(blob),payload_bits=len(bits),table_bytes=n*128,header_bytes=len(hdr),saving=len(raw)-len(blob),roundtrip=True);out.append(a);print(a,flush=True)
    return out
if __name__=='__main__':
    out=run('first')+run('second');(ROOT/'entropy.json').write_text(json.dumps(out,indent=2))
