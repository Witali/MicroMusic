"""Speech frames reference shared Q4 spectral/voice patterns.

Each eight-byte Flash record contains eight signed Q4 reflections and a
waveform index embedded in the high bits of the biased first coefficient.
Pitch, half-sample period, gain and duration remain independently controlled.
"""
import numpy as np
from numba import njit
from q3_pulsebook import signed

SCHEMA='q4-voice-patterns-v1'


def validate(pitches,gains,indices,durations,halves,patterns,modes,waves):
    p,g,i,d,h,k,m,b=map(np.asarray,(pitches,gains,indices,durations,halves,patterns,modes,waves))
    if any(a.dtype.kind not in 'iu' for a in (p,g,i,d,h,k,m,b)):
        raise ValueError('Voice-pattern fields must be integers')
    if (p.ndim!=1 or not len(p) or any(a.shape!=p.shape for a in (g,i,d,h))
            or np.any(p<0) or np.any(p>126) or np.any(g<0) or np.any(g>15)
            or not np.all(np.isin(h,[0,1])) or np.any((p==0)&(h!=0))
            or not np.all(np.isin(d,[64,128,192,256]))):
        raise ValueError('Invalid voice-pattern frame controls')
    if (k.ndim!=2 or k.shape[1]!=8 or not 1<=len(k)<=32 or np.any(k < -15) or np.any(k>15)
            or m.shape!=(len(k),) or np.any(m<0) or np.any(m>7)
            or np.any(i<0) or np.any(i>=len(k))
            or b.shape!=(8,16) or np.any(b < -7) or np.any(b>7)):
        raise ValueError('Invalid stable Q4 patterns, indices or waveforms')
    return p,g,i,d,h,k,m,b


def pack_patterns(patterns,modes):
    k,m=np.asarray(patterns),np.asarray(modes)
    if (k.dtype.kind not in 'iu' or m.dtype.kind not in 'iu' or k.ndim!=2 or k.shape[1]!=8
            or not 1<=len(k)<=32 or m.shape!=(len(k),) or np.any(k < -15) or np.any(k>15)
            or np.any(m<0) or np.any(m>7)):
        raise ValueError('Expected 1..32 stable Q4 voice patterns')
    encoded=k.astype(np.int16)&255
    encoded[:,0]=(k[:,0]+16)|(m<<5)
    return encoded.astype(np.uint8).tobytes()


def unpack_patterns(payload):
    if not len(payload) or len(payload)%8 or len(payload)>256:raise ValueError('Invalid pattern table size')
    raw=np.frombuffer(payload,np.uint8).reshape(-1,8)
    k=raw.view(np.int8).copy();k[:,0]=(raw[:,0]&31).astype(np.int16)-16
    m=raw[:,0]>>5
    pack_patterns(k,m)
    return k,m


def pack_stream(pitches,gains,indices,durations,halves):
    p,g,i,d,h=map(np.asarray,(pitches,gains,indices,durations,halves))
    validate(p,g,i,d,h,np.zeros((32,8),np.int8),np.zeros(32,np.uint8),np.zeros((8,16),np.int8))
    out=bytearray()
    for pitch,gain,index,duration,half in zip(p,g,i,d,h):
        pitch,gain,index,duration,half=map(int,(pitch,gain,index,duration,half))
        if pitch<=63 and duration!=192 and not half and index<16:out.append((duration&192)|pitch)
        else:out.extend((192|((duration//64)&3)|((index>>4)<<2),pitch|(half<<7)))
        out.append(((index&15)<<4)|gain)
    return bytes(out)


def unpack_stream(payload):
    raw=bytes(payload);offset=0;p=[];g=[];i=[];d=[];h=[]
    def byte():
        nonlocal offset
        if offset==len(raw):raise ValueError('Truncated pattern stream')
        v=raw[offset];offset+=1;return v
    while offset<len(raw):
        header=byte()
        if header==255:raise ValueError('EOF must be omitted')
        if header&192==192:
            if header&56:raise ValueError('Unknown pattern header bits')
            duration=(header&3)*64 or 256;high=(header&4)<<2
            pitch=byte();half=pitch>>7;pitch&=127
        else:duration=(header&192) or 256;pitch=header&63;half=high=0
        value=byte();p.append(pitch);g.append(value&15);i.append((value>>4)|high);d.append(duration);h.append(half)
    values=tuple(np.asarray(a,dtype=np.uint16 if n==3 else np.uint8) for n,a in enumerate((p,g,i,d,h)))
    pack_stream(*values)
    return values


@njit(cache=True)
def multiply(value,coefficient):
    value=signed(value)
    if coefficient<0:value=signed(-value)
    return signed((value*abs(coefficient))>>4)


@njit(cache=True)
def render(pitches,gains,indices,durations,halves,patterns,modes,waves):
    output=np.empty(int(durations.sum()),np.uint8)
    states=np.zeros(8,np.int32);coefficients=np.zeros(8,np.int32);counts=np.zeros(4,np.int64)
    seed,phase,frame,next_t=0xa7,1,0,int(durations[0])-1
    period=gain=mode=previous=cycle_extra=half=0
    for t in range(len(output)):
        if t==0 or t==next_t:
            if t:
                frame+=1
                if frame==len(pitches):frame=0
                next_t+=int(durations[frame])
            period=int(pitches[frame]);half=int(halves[frame]);cycle_extra=0;phase=period
            gain=int(gains[frame]);index=int(indices[frame]);mode=int(modes[index])
            for j in range(8):coefficients[j]=int(patterns[index,j])
        ex=0
        if period:
            phase=(phase-1)&255
            if not phase:
                cycle_extra^=half;phase=period+cycle_extra;ex=int(waves[mode,0])*gain
            else:
                lag=period+cycle_extra-phase
                if lag<16:ex=int(waves[mode,lag])*gain
        else:
            low=seed&1;seed>>=1
            if low:seed^=0xb8
            ex=-gain if seed&1 else gain
        for j in range(7,-1,-1):
            old,coefficient=states[j],coefficients[j]
            counts[2]+=int(old==-128 and coefficient<0)
            raw=ex-multiply(old,coefficient);counts[0]+=int(raw < -128 or raw>127);ex=signed(raw)
            if j<7:
                counts[2]+=int(ex==-128 and coefficient<0)
                raw=old+multiply(ex,coefficient);counts[1]+=int(raw < -128 or raw>127);states[j+1]=signed(raw)
        states[0]=ex
        raw=ex+previous-(previous>>1);counts[3]+=int(raw < -128 or raw>127);previous=signed(raw)
        output[t]=(previous+128)&255
    return output,counts


@njit(cache=True)
def envelope_features(patterns):
    """Floating lattice impulse responses for clustering, not final scoring."""
    result=np.empty((len(patterns),512),np.float64)
    for row in range(len(patterns)):
        state=np.zeros(8,np.float64)
        for t in range(512):
            ex=1. if t==0 else 0.
            for j in range(7,-1,-1):
                k=patterns[row,j]/16.;old=state[j];ex-=old*k
                if j<7:state[j+1]=old+ex*k
            state[0]=ex;result[row,t]=ex
    return result


def pack_selective(pitches,gains,indices,durations,halves,heads,tails,modes,waves):
    """PC-only candidate: two Q4 coefficients per frame, six shared Q3 ones.

    The two least significant Q4 bits form a separate 2-bit/frame plane.
    Their four-bit quotients share one byte in each ordinary pattern packet.
    Each tail record holds six Q3 nibbles and one waveform-selector byte.
    No decoder, EOF or waveform bytes are included in these three sections.
    """
    head,tail=np.asarray(heads),np.asarray(tails)
    if (head.dtype.kind not in 'iu' or tail.dtype.kind not in 'iu'
            or head.shape!=(len(pitches),2) or tail.ndim!=2 or tail.shape[1]!=6
            or not 1<=len(tail)<=16 or np.any(head < -15) or np.any(head>15)
            or np.any(tail < -14) or np.any(tail>14) or np.any(tail%2)):
        raise ValueError('Selective patterns require two Q4 heads and 1..16 six-Q3 tails')
    p,g,i,d,h,_,m,b=validate(pitches,gains,indices,durations,halves,
        np.column_stack((np.zeros((len(tail),2),np.int8),tail)),modes,waves)
    table=bytearray()
    for row,mode in zip(tail,m):
        q=row.astype(np.int16)//2+8
        table.extend((int(q[0]|q[1]<<4),int(q[2]|q[3]<<4),int(q[4]|q[5]<<4),int(mode)))
    out=bytearray();plane=bytearray((len(p)+3)//4)
    for n,(pitch,gain,index,duration,half) in enumerate(zip(p,g,i,d,h)):
        out.extend(pack_stream(np.array([pitch]),np.array([gain]),np.array([index]),
            np.array([duration]),np.array([half])))
        q=head[n].astype(np.int16)//2+8
        out.append(int(q[0]|q[1]<<4))
        plane[n//4]|=int((head[n,0]&1)|((head[n,1]&1)<<1))<<((n%4)*2)
    return bytes(table),bytes(plane),bytes(out)


def unpack_selective(table,plane,payload):
    """Decode the exact PC-study layout; fail on padding or trailing bytes."""
    if not len(table) or len(table)%4 or len(table)>64:raise ValueError('Invalid tail table size')
    if not payload:raise ValueError('Empty selective stream')
    rows=np.frombuffer(table,np.uint8).reshape(-1,4);tails=np.empty((len(rows),6),np.int8)
    tails[:,::2]=((rows[:,:3]&15).astype(np.int16)-8)*2
    tails[:,1::2]=((rows[:,:3]>>4).astype(np.int16)-8)*2
    modes=rows[:,3].copy();offset=0;controls=[];heads=[]
    while offset<len(payload):
        header=payload[offset];size=3 if header&192==192 else 2
        if offset+size>=len(payload):raise ValueError('Truncated selective stream')
        frame=unpack_stream(payload[offset:offset+size]);offset+=size
        controls.append([int(a[0]) for a in frame]);q=payload[offset];offset+=1
        heads.append([(q&15)*2-16,(q>>4)*2-16])
    if len(plane)!=(len(heads)+3)//4:raise ValueError('Invalid precision plane size')
    if len(heads)%4 and plane and plane[-1]>>(2*(len(heads)%4)):
        raise ValueError('Nonzero precision plane padding')
    head=np.asarray(heads,np.int8)
    for n in range(len(head)):
        bits=plane[n//4]>>((n%4)*2);head[n,0]+=bits&1;head[n,1]+=(bits>>1)&1
    values=tuple(np.asarray(a,np.uint16 if n==3 else np.uint8)
        for n,a in enumerate(zip(*controls)))
    waves=np.zeros((8,16),np.int8)
    pack_selective(*values,head,tails,modes,waves)
    return (*values,head,tails,modes)
