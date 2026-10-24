"""Exact PC format: three 16-record dictionaries for 2/3/3 reflections.

All records are 16-bit little endian. A root holds two Q4 coefficients, pulse
selector and a gain-window selector. Frames hold three indices and local gain.
The 96 table bytes and frame bytes exclude decoder, EOF and waveform storage.
"""
import numpy as np

SCHEMA='q4-product233-v1'
OFFSETS=np.array([0,2,4,6,8,10,12,16],np.int16)


def tables(root,middle,tail):
    r,a,b=map(np.asarray,(root,middle,tail))
    if (any(v.dtype.kind not in 'iu' for v in (r,a,b)) or r.shape!=(16,4)
            or a.shape!=(16,3) or b.shape!=(16,3) or np.any(r[:,:2] < -15)
            or np.any(r[:,:2]>15) or np.any(r[:,2:]<0) or np.any(r[:,2:]>7)
            or np.any(a < -15) or np.any(a>15) or np.any(b < -15) or np.any(b>15)):
        raise ValueError('Invalid sixteen-record Q4 dictionaries')
    return r,a,b


def pack_tables(root,middle,tail):
    r,a,b=(v.astype(np.int64) for v in tables(root,middle,tail))
    words=[(r[:,0]+16)|((r[:,1]+16)<<5)|(r[:,2]<<10)|(r[:,3]<<13)]
    for v in (a,b):words.append((v[:,0]+16)|((v[:,1]+16)<<5)|((v[:,2]+16)<<10))
    return np.concatenate(words).astype('<u2').tobytes()


def unpack_tables(payload):
    if len(payload)!=96:raise ValueError('Expected exactly 96 table bytes')
    r,a,b=np.frombuffer(payload,dtype='<u2').astype(np.int32).reshape(3,16)
    if np.any(a&32768) or np.any(b&32768):raise ValueError('Reserved dictionary bits')
    root=np.column_stack(((r&31)-16,((r>>5)&31)-16,(r>>10)&7,r>>13)).astype(np.int16)
    decode=lambda x:np.column_stack(((x&31)-16,((x>>5)&31)-16,((x>>10)&31)-16)).astype(np.int16)
    middle,tail=decode(a),decode(b);tables(root,middle,tail)
    return root,middle,tail


def controls(pitches,gains,durations,indices,halves):
    p,g,d,i,h=map(np.asarray,(pitches,gains,durations,indices,halves))
    if (any(v.dtype.kind not in 'iu' for v in (p,g,d,i,h)) or p.ndim!=1 or not len(p)
            or any(v.shape!=p.shape for v in (g,d,h)) or i.shape!=(len(p),3)
            or np.any(p<0) or np.any(p>126) or np.any(g<0) or np.any(g>15)
            or np.any(i<0) or np.any(i>15) or not np.all(np.isin(h,[0,1]))
            or np.any((p==0)&(h!=0)) or not np.all(np.isin(d,[64,128,192,256]))):
        raise ValueError('Invalid product-dictionary frame controls')
    return p,g,d,i,h


def pack_frames(pitches,gains,durations,indices,halves):
    p,g,d,i,h=controls(pitches,gains,durations,indices,halves);out=bytearray()
    for pitch,gain,duration,index,half in zip(p,g,d,i,h):
        pitch,gain,duration,half=map(int,(pitch,gain,duration,half))
        if pitch<=63 and duration!=192 and not half:out.append((duration&192)|pitch)
        else:out.extend((192|((duration//64)&3),pitch|(half<<7)))
        out.extend(((int(index[0])<<4)|gain,(int(index[1])<<4)|int(index[2])))
    return bytes(out)


def unpack_frames(payload):
    raw=bytes(payload);offset=0;frames=[]
    def byte():
        nonlocal offset
        if offset>=len(raw):raise ValueError('Truncated product-dictionary stream')
        v=raw[offset];offset+=1;return v
    while offset<len(raw):
        header=byte()
        if header&192==192:
            if header&60:raise ValueError('Unknown product header or EOF')
            duration=(header&3)*64 or 256;pitch=byte();half=pitch>>7;pitch&=127
        else:duration=(header&192) or 256;pitch=header&63;half=0
        first,second=byte(),byte()
        frames.append((pitch,first&15,duration,[first>>4,second>>4,second&15],half))
    if not frames:raise ValueError('Empty product-dictionary stream')
    values=tuple(np.asarray(a,np.int16) for a in zip(*frames));controls(*values);return values


def expand(pitches,gains,durations,indices,halves,root,middle,tail):
    p,g,d,i,h=controls(pitches,gains,durations,indices,halves);r,a,b=tables(root,middle,tail)
    chosen=r[i[:,0]];actual=g+OFFSETS[chosen[:,3]]
    if np.any(actual>30):raise ValueError('Gain window exceeds physical gain range')
    coefficients=np.column_stack((chosen[:,:2],a[i[:,1]],b[i[:,2]])).astype(np.int16)
    return p,actual,d,coefficients,chosen[:,2],h
