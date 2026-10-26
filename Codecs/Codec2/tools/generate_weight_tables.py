#!/usr/bin/env python3
"""Quantize all pinned KISS twiddles, retaining original binary32 angles."""
from pathlib import Path
import argparse,re
ROOT=Path(__file__).resolve().parents[1]
DESTINATION=ROOT/'src/fixed_weight_tables.inc'
def generate():
    original=(ROOT/'src/compact_tables.inc').read_text()
    values=[float.fromhex(s[:-1]) for s in re.findall(r'-?0x[0-9a-f.]+p[+-]\d+f',original)][:768]
    assert len(values)==768
    result=original.split('*/',1)[0]+'*/\n/* Quantized pinned binary32 KISS twiddles; forward direction. */\n'
    for q in [14,22,30]:
        result+=f'#if CODEC2_WEIGHT_TWIDDLE_Q == {q}\n'
        for name,data in [('weight_twiddle',values[:512]),('weight_super',values[512:])]:
            numbers=[round(v*(1<<q)) for v in data]
            result+=f'static const int{16 if q==14 else 32}_t {name}[{len(data)}] CODEC2_TABLE_STORAGE = {{\n'
            for at in range(0,len(data),8):result+='    '+', '.join(str(n) for n in numbers[at:at+8])+',\n'
            result+='};\n'
        result+='#endif\n'
    return result.encode('utf-8')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');a=p.parse_args();data=generate()
    if a.check:assert DESTINATION.read_bytes()==data
    else:DESTINATION.write_bytes(data)
