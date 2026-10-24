"""Byte-aligned Q4 updates with an optional parity-mask escape per half.

Four even Q4 coefficients use the old two-byte Q3 representation. An odd value
adds a mask byte: its unused zero low nibble marks the escape. Previous halves
are reused exactly. This defines data only, without an AVR size/timing claim.
"""
import numpy as np

SCHEMA='q4-sparse-stream-v1'
QUARTER_SCHEMA='q4-quarter-sparse-stream-v1'


def pack_half(coefficients):
    k=np.asarray(coefficients)
    if k.shape!=(4,) or k.dtype.kind not in 'iu' or np.any(k < -15) or np.any(k>15):
        raise ValueError('Expected four stable signed Q4 coefficients')
    codes=k.astype(np.int16)//2+8;mask=sum(int(k[j]&1)<<j for j in range(4))
    data=bytes((int(codes[0]|(codes[1]<<4)),int(codes[2]|(codes[3]<<4))))
    return bytes([mask<<4])+data if mask else data


def unpack_half(data):
    if len(data)<2:raise ValueError('Truncated Q4 half')
    if data[0]&15:mask=0;raw=data[:2];used=2
    else:
        if len(data)<3 or data[0]==0:raise ValueError('Invalid Q4 escape')
        mask=data[0]>>4;raw=data[1:3];used=3
    k=np.asarray([(raw[j//2]>>(4*(j%2))&15)*2-16+((mask>>j)&1) for j in range(4)],np.int8)
    pack_half(k)
    return k,used


def validate(pitches,gains_q1,durations,coefficients,modes,halves,pitch_bits=1):
    if pitch_bits not in (1,2):raise ValueError('Expected one-bit or two-bit pitch fractions')
    p,g,d,k,m,h=tuple(map(np.asarray,(pitches,gains_q1,durations,coefficients,modes,halves)))
    if any(x.dtype.kind not in 'iu' for x in (p,g,d,k,m,h)):
        raise ValueError('Q4 stream fields must be integers')
    if (p.ndim!=1 or not len(p) or any(x.shape!=p.shape for x in (g,d,m,h))
            or k.shape!=(len(p),8) or np.any(p<0) or np.any(p>126)
            or np.any(g<0) or np.any(g>30) or np.any(k < -15) or np.any(k>15)
            or np.any(m<0) or np.any(m>7) or np.any(h<0) or np.any(h>=(1<<pitch_bits))
            or np.any((p==0)&(h!=0)) or not np.all(np.isin(d,[64,128,192,256]))):
        raise ValueError('Invalid Q4 stream fields')
    return p,g,d,k,m,h


def pack(pitches,gains_q1,durations,coefficients,modes,halves,pitch_bits=1):
    p,g,d,k,m,h=validate(pitches,gains_q1,durations,coefficients,modes,halves,pitch_bits)
    out=bytearray();previous=None
    for n in range(len(p)):
        pitch,gain,duration,mode,half=map(int,(p[n],g[n],d[n],m[n],h[n]))
        low=previous is None or not np.array_equal(k[n,:4],previous[:4])
        high=previous is None or not np.array_equal(k[n,4:],previous[4:])
        kind=0 if low and high else 1 if low else 2 if high else 3
        selector=(mode<<2)|kind
        if pitch<=63 and duration!=192 and not half and selector<16 and gain<16:
            out.append((duration&192)|pitch)
        else:
            fraction_high=half if pitch_bits==1 else half>>1
            extra=0 if pitch_bits==1 else (half&1)<<4
            out.extend((192|((duration//64)&3)|((selector>>4)<<2)|((gain>>4)<<3)|extra,pitch|(fraction_high<<7)))
        out.append(((selector&15)<<4)|(gain&15))
        if low:out.extend(pack_half(k[n,:4]))
        if high:out.extend(pack_half(k[n,4:]))
        previous=k[n]
    return bytes(out)


def unpack(data,pitch_bits=1):
    if pitch_bits not in (1,2):raise ValueError('Expected one-bit or two-bit pitch fractions')
    raw=bytes(data);offset=0;frames=[];previous=np.zeros(8,np.int8)
    def byte():
        nonlocal offset
        if offset>=len(raw):raise ValueError('Truncated Q4 stream')
        value=raw[offset];offset+=1;return value
    while offset<len(raw):
        header=byte()
        if header&192==192:
            if header&(48 if pitch_bits==1 else 32):raise ValueError('Unknown Q4 header or EOF')
            duration=(header&3)*64 or 256;selector_high=(header&4)<<2;gain_high=(header&8)<<1
            pitch=byte();half=pitch>>7;pitch&=127
            if pitch_bits==2:half=(half<<1)|((header>>4)&1)
        else:
            duration=(header&192) or 256;pitch=header&63;half=selector_high=gain_high=0
        value=byte();selector=(value>>4)|selector_high;gain=(value&15)|gain_high
        mode=selector>>2;kind=selector&3;k=previous.copy()
        if not frames and kind!=0:raise ValueError('First frame must define both coefficient halves')
        for start,changed in ((0,kind in (0,1)),(4,kind in (0,2))):
            if changed:
                half_k,used=unpack_half(raw[offset:]);offset+=used;k[start:start+4]=half_k
        frames.append((pitch,gain,duration,k.copy(),mode,half));previous=k
    if not frames:raise ValueError('Empty Q4 stream')
    values=tuple(np.asarray(a,np.int16) for a in zip(*frames));validate(*values,pitch_bits)
    return values
