"""Self-contained assembly parser and Codec2-3200 reference bit-field extractor."""
from pathlib import Path
import re

def parse_asm(path):
    src=path.read_text()
    sym={}
    for n,v in re.findall(r'^\.equ\s+(\w+)\s*,\s*(0x[0-9a-fA-F]+|\d+)',src,flags=re.M):sym[n]=int(v,0)
    inst=[];labels={};addr=0
    for line in src.splitlines():
        line=line.split('/*',1)[0].split('//',1)[0].strip()
        if not line or line.startswith(('.', '*')):continue
        if line.endswith(':'):
            labels[line[:-1]]=len(inst);continue
        if line.startswith('/*') or line.startswith('*/'):continue
        # 'sbiw ..., ...' etc
        parts=line.strip().split(None,1)
        op=parts[0].lower()
        args=[x.strip() for x in parts[1].split(',')] if len(parts)>1 else []
        inst.append((op,args,addr))
        addr+=4 if op in ('sts','lds') else 2
    return inst,labels,sym


def fields(frame:bytes):
    assert len(frame)==8
    bitpos=0
    def take(n):
        nonlocal bitpos
        gr=0
        for _ in range(n):
            gr=(gr<<1)|((frame[bitpos>>3]>>(7-(bitpos&7)))&1)
            bitpos+=1
        z=gr
        z^=z>>1; z^=z>>2;z^=z>>4
        return z
    v0=take(1);v1=take(1);p=take(7);e=take(5)
    lsp=[take(5) for _ in range(10)]
    assert bitpos==64
    return v0,v1,p,e,lsp

