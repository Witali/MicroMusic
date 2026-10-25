#!/usr/bin/env python3
"""LPX3 v7: lossless bitstream + true native C++ PCM regression to original v1.

Requires only Python3 standard library and g++/clang++. Never assumes that
AVR object compilation implies hardware real-time performance.
"""
import sys,os,subprocess,tempfile,hashlib,json,random,struct,collections,argparse
from pathlib import Path
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'tools'))
from l3av_parse import unpack
from rice_v3 import BitWriter
from rice_v7 import encode_v7, decode_v7, verify_eq


def build(out):
    specs=[('v1',P/'reference_v1'/'Lpx3AvrCore.cpp',P/'reference_v1'/'decode_host.cpp'),
           ('v7',P/'src'/'Lpx3AvrCore.cpp',P/'tests'/'decode_host.cpp')]
    for name,core,driver in specs:
        cmd=['g++','-O2','-std=c++17','-fno-strict-aliasing',str(core),str(driver),'-o',str(out/name)]
        subprocess.run(cmd,check=True,capture_output=True)


def gen(seed):
    r=random.Random(seed)
    n=r.choice([1,7,20,79,80,81,159,160,161,320,480,639,800,960,1280,1800])
    raw=bytearray(struct.pack('<4sBBHIHHHH',b'L3AV',1,3,8000,n,r.randrange(0,8000),r.randrange(0,4000),160,80))
    lsfs=[140+i*75 for i in range(10)]
    first=True
    nblocks=0
    for frame in range((n+159)//160):
        if first or r.randrange(7)==0:
            if not first:
                lsfs=[min(1023,max(0,x+r.randrange(-12,13))) for x in lsfs]
            data=sum(int(v)<<(10*i) for i,v in enumerate(lsfs)).to_bytes(13,'little')
            raw.extend(bytes([5])+data);first=False
        elif r.randrange(3)==0:
            raw.append(0)
        else:
            d=[r.choice([-32,-3,-2,-1,0,0,0,1,2,3,32]) for _ in range(10)]
            lsfs=[min(1023,max(0,x+y)) for x,y in zip(lsfs,d)]
            # Always apply exactly the quantized deltas.
            raw.extend(bytes([6])+bytes(int(x)&255 for x in d))
            # Correct for clamping: the values above are inside 0..1023 by construction.
        for _ in range(2):
            remain=n-nblocks*80
            if remain<=0:break
            count=min(80,remain);nblocks+=1
            bits=r.choice([0,2,3,4,5,6]);scale=r.randrange(1,256)
            raw.extend(bytes([bits,scale]))
            w=BitWriter()
            for _ in range(count):
                if bits==0:continue
                x=r.randrange(1<<bits)
                w.put(x,bits)
            w.aligned();raw.extend(w.get())
    return bytes(raw)


def check_one(raw,t,old,new,label):
    source=t/(label+'_v1.l3av');source.write_bytes(raw)
    doc=unpack(raw)
    coded,stats=encode_v7(doc);verify_eq(doc,coded)
    target=t/(label+'_v7.l3av');target.write_bytes(coded)
    a=t/(label+'_v1.pcm8');b=t/(label+'_v7.pcm8')
    r1=subprocess.run([str(old),str(source),str(a)],capture_output=True)
    r2=subprocess.run([str(new),str(target),str(b)],capture_output=True)
    assert r1.returncode==0,(label,'ref',r1.stderr.decode(errors='replace'))
    assert r2.returncode==0,(label,'new',r2.stderr.decode(errors='replace'))
    assert a.read_bytes()==b.read_bytes(),(label,'PCM mismatch')
    assert len(b.read_bytes())==doc['sampleCount']
    return dict(name=label,original_bytes=len(raw),new_bytes=len(coded),samples=doc['sampleCount'],sha256=hashlib.sha256(b.read_bytes()).hexdigest(), **{k:v for k,v in stats.items() if k.startswith('delta_')})


def run(fuzz,private):
    with tempfile.TemporaryDirectory() as d:
        t=Path(d);build(t);old=t/'v1';new=t/'v7';rows=[]
        syn=P/'examples'/'synthetic_v1.l3av'
        if syn.exists():
            if syn.read_bytes()[5]==3:
                rows.append(check_one(syn.read_bytes(),t,old,new,'synthetic'))
        for i in range(fuzz):
            rows.append(check_one(gen(20261023+i),t,old,new,'generated_%04d'%i))
        for i,file in enumerate(private):
            rows.append(check_one(Path(file).read_bytes(),t,old,new,'private_%d'%i))
        good=(t/(rows[-1]['name']+'_v7.l3av')).read_bytes()
        invalid={
            'bad_version':good[:4]+bytes([4])+good[5:],
            'bad_flags':good[:5]+bytes([0])+good[6:],
            'bad_rate':good[:6]+bytes([1,0])+good[8:],
            'truncated':good[:max(20,len(good)//2)],
        }
        for name,bad in invalid.items():
            p=t/(name+'.l3av');p.write_bytes(bad)
            got=subprocess.run([str(new),str(p),str(t/(name+'.pcm8'))],capture_output=True)
            assert got.returncode!=0,(name,'incorrectly accepted')
        for row in rows[-len(private):] if private else rows[:1]:print(json.dumps(row,ensure_ascii=False))
        print(f'PASS {len(rows)} independent original-v1 to v7 PCM comparisons; {len(invalid)} negative cases')
        return rows

if __name__=='__main__':
    x=argparse.ArgumentParser();x.add_argument('--fuzz',type=int,default=100);x.add_argument('--private',nargs='*',default=[]);a=x.parse_args();run(a.fuzz,a.private)
