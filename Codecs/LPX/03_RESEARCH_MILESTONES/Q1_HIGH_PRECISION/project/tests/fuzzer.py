# Deterministic input generator, borrowed from LPX3 v7 test suite.
import random,struct
from rice_v3 import BitWriter
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

