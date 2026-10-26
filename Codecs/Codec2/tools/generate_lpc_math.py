#!/usr/bin/env python3
"""Generate the integer cosine polynomial and canonical Codec2 angle constants."""
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from pathlib import Path
import math,struct
ROOT=Path(__file__).resolve().parents[1]
def generate():
    with localcontext() as ctx:
        ctx.prec=90
        pi=Decimal('3.14159265358979323846264338327950288419716939937510582097494459230781640628620899')
        quantize=lambda x,q:int((x*(1<<q)).to_integral_value(rounding=ROUND_HALF_EVEN))
        values=[quantize(Decimal((-1)**i)/math.factorial(2*i+1),60) for i in range(10)]
        # This literal is the pinned upstream defines.h PI, distinct from true pi.
        grid=quantize(Decimal('3.141592654')/160,54)
        header='/* Project-generated mathematical constants; Q60 sine/x Taylor degree18.\n * Grid angle uses pinned Codec2 PI literal 3.141592654, not true pi. */\n'
        for name,value in [('LPC_PI_Q60',pi),('LPC_TWO_PI_Q60',2*pi),('LPC_HALF_PI_Q60',pi/2)]:header+=f'#define {name} INT64_C({quantize(value,60)})\n'
        header+=f'#define LPC_GRID_Q54 UINT64_C({grid})\nstatic const int64_t lpc_sine_coefficient[10] CODEC2_TABLE_STORAGE = {{\n    '+', '.join(f'INT64_C({v})' for v in values)+'\n};\n'
        initial=[struct.unpack('<I',struct.pack('<f',i*3.141592654/11))[0] for i in range(10)]
        header+='static const uint32_t lpc_initial_bits[10] CODEC2_TABLE_STORAGE = {\n    '+', '.join(f'UINT32_C(0x{x:08x})' for x in initial)+'\n};\n'
        return header.encode('ascii')
if __name__=='__main__':(ROOT/'src/lpc_math_tables.inc').write_bytes(generate())
