from csv import DictReader
from pathlib import Path

def first_w3(poly,maxb=5000):
    v=1;previous={}
    for b in range(maxb+1):
        if v in previous: return (b,0,previous[v],b)
        if b: previous[v ^ 1]=b
        v=((v<<1)^ (poly if (v&0x8000) else 0))&65535
    return None

def first_w4(poly,maxb=900):
    v=1;lookup={}; prev=[]
    for b in range(maxb+1):
        target=1^v
        if target in lookup:
            a,c=lookup[target]
            return (b,(0,a,c,b))
        if b:
            for a,old in enumerate(prev):
                if a: lookup.setdefault(old^v,(a,b))
        prev.append(v)
        v=((v<<1)^(poly if v&0x8000 else 0))&65535
    return None

rows=list(DictReader((Path(__file__).resolve().parents[1]/'data'/'all_32768_polynomials.csv').open()))
pool=[r for r in rows if int(r['degree_low'])<=8 and int(r['has_x_plus_one'])==1 and int(r['period_bits'])>=16384]
for r in pool:
    p=int(r['poly_hex'],16)
    w4=first_w4(p)
    print(f'{r["poly_hex"]} period={r["period_bits"]} lowHW={r["low_popcount"]} 4bit_first_span={w4[0]+1 if w4 else "??"} pattern={w4[1] if w4 else "?"}')
print('KEY POLYS')
for p in [0x0007,0x0009,0x001b,0x002d,0x0031,0x0039,0x001f,0x003b,0x000f,0x0081,0x1021,0x8005,0xa2eb]:
 print(f'{p:04x} 3bit span={first_w3(p)} 4bit span={first_w4(p)}')
