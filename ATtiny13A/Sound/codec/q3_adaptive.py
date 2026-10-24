"""Exact per-recording form compaction and complete Flash/EEPROM selection.

The logical model remains eight rows. Unreferenced physical rows can be reused
for the speech prefix; four-form machine code is sufficient at <=4 active rows.
"""
import numpy as np
import q3_pulsebook8 as codec
from q3_short_eeprom import code_bytes


def compact(frames,durations,book):
    codec.validate(frames,durations,book)
    f=codec.canonicalize_selectors(frames,book)
    b=np.asarray(book)
    active=(f[:,0]>0)&((f[:,1]&15)>0)
    modes=f[:,1]>>4
    used=np.unique(modes[active]).tolist()
    # Four cheap selectors should go to rows that otherwise force an escape.
    compact_header=active&(f[:,0]<=63)&(np.asarray(durations)!=192)
    order=sorted(used,key=lambda m:(-int(np.sum(compact_header&(modes==m))),
        -int(np.sum(active&(modes==m))),m))
    count=max(1,len(order))
    result=np.zeros((8,16),np.int8)
    mapping=np.zeros(8,np.uint8)
    for new,old in enumerate(order):
        result[new]=b[old];mapping[old]=new
    f[:,1]=(f[:,1]&15)|(mapping[modes]<<4)
    return f,result,dict(active_forms=len(order),stored_forms=count,
        decoder_forms=4 if count<=4 else 8,source_rows=order)


def layouts(frames,durations,book):
    f,b,info=compact(frames,durations,book)
    payload=codec.validate(f,durations,b)
    for width in (4,8,16):
        if np.any(b[:,width:]):continue
        for packing in ('raw','nibble'):
            stride=width if packing=='raw' else width//2
            # Encode through the already qualified four-row primitive, then
            # retain only reachable rows. A removed row is never addressed by
            # a voiced, nonzero-gain frame; inactive frames select row zero.
            encoded=(codec.encode_four(b[:4],width,packing)+codec.encode_four(b[4:],width,packing))[:info['stored_forms']*stride]
            if len(encoded)>64:continue
            prefix=min(64-len(encoded),len(payload))
            code=code_bytes(width,packing,prefix)
            if info['decoder_forms']==8:code+=10+2*(stride.bit_length()-1)
            suffix=payload[prefix:]
            yield dict(info,width=width,packing=packing,book_bytes=len(encoded),
                prefix_bytes=prefix,prefix_start=len(encoded),prefix_end=len(encoded)+prefix,
                eeprom=(encoded+payload[:prefix]).ljust(64,b'\xff'),flash_suffix=suffix,
                code_bytes=code,flash_bytes=(code+len(suffix)+2)&~1,
                maximum_stream_bytes=1024-code-1+prefix,stream_bytes=len(payload),
                frames=f,book=b,payload=payload)


def select(frames,durations,book):
    candidates=list(layouts(frames,durations,book))
    if not candidates:raise ValueError('No physical pulsebook fits EEPROM')
    return min(candidates,key=lambda x:(x['flash_bytes'],x['code_bytes'],x['book_bytes'],x['width'],x['packing']))
