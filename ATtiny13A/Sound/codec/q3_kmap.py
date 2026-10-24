"""Tagged Q3 lattice with separate sixteen-entry Q7 maps for K1 and K2.

The optimizer uses a6x16 integer table: four signed4-bit waveforms followed
by two signedQ7 coefficient maps. Actual EEPROM contains32 packed waveform
bytes followed by32 map bytes. Arithmetic keeps the frozen byte-negation and
rounding convention; a uniform map reproduces all valid old Q3 coefficients.
"""
import numpy as np
from numba import njit
from hq4_core import pack_stream
import q3_pulsebook as base

SCHEMA = 'hq4-q3-kmap-v1'


def legacy_tables():
    maps = np.tile((np.arange(16,dtype=np.int16)-8)*16,(2,1))
    maps[:,0] = -127
    return np.vstack((base.legacy_tables(),maps)).astype(np.int8)


def validate_tables(tables):
    values = np.asarray(tables)
    if (values.shape != (6,16) or values.dtype.kind not in 'iu'
            or np.any(values[:4] < -7) or np.any(values[:4] > 7)
            or np.any(values[4:] < -127) or np.any(values[4:] > 127)):
        raise ValueError('Expected four signed4-bit waveforms and two stable signedQ7 maps')
    return values


def pack_eeprom(tables):
    values = validate_tables(tables)
    wave = values[:4].astype(np.int16).ravel()+8
    packed = (wave[::2]|(wave[1::2]<<4)).astype(np.uint8).tobytes()
    return packed+values[4:].astype(np.int8).tobytes()


def unpack_eeprom(payload):
    if len(payload) != 64:
        raise ValueError('Expected exactly64 EEPROM bytes')
    raw = np.frombuffer(payload[:32],np.uint8)
    wave = np.empty(64,np.int16)
    wave[::2],wave[1::2] = (raw&15).astype(np.int16)-8,(raw>>4).astype(np.int16)-8
    values = np.vstack((wave.reshape(4,16),np.frombuffer(payload[32:],np.int8).reshape(2,16)))
    validate_tables(values)
    return values.astype(np.int8)


def validate(frames,durations,tables,samples=None,stream_budget=None):
    f,d = np.asarray(frames),np.asarray(durations)
    validate_tables(tables)
    if (f.ndim != 2 or f.shape[1] != 6 or not len(f) or f.dtype.kind not in 'iu'
            or d.shape != (len(f),) or d.dtype.kind not in 'iu'
            or np.any(f < 0) or np.any(f > 255) or np.any(f[:,0] > 126)
            or np.any(f[:,1] > 63) or not np.all(np.isin(d,[64,128,192,256]))
            or np.any((f[:,3:]&15) == 0) or np.any((f[:,3:]>>4) == 0)):
        raise ValueError('Invalid Kmap frames or unstable fixed-Q3 coefficient')
    if samples is not None and int(d.sum()) != samples:
        raise ValueError('Kmap model must preserve complete reference duration')
    payload = pack_stream(f,d)
    if stream_budget is not None and len(payload) > stream_budget:
        raise ValueError('Packed stream exceeds specified profile budget')
    return payload


@njit(cache=True)
def multiply(value,coefficient,nearest):
    value = base.signed(value)
    if coefficient < 0:
        value = base.signed(-value)
    return base.signed((value*abs(coefficient)+(64 if nearest else 0)) >> 7)


@njit(cache=True)
def render(frames,durations,tables,tilt_shift=1,nearest=False):
    output = np.empty(int(durations.sum()),np.uint8)
    states,coefficients = np.zeros(8,np.int32),np.zeros(8,np.int32)
    counts = np.zeros(4,np.int64)
    seed,phase,frame,next_t = 0xa7,1,0,int(durations[0])-1
    period = gain = mode = previous = 0
    for t in range(len(output)):
        if t == 0 or t == next_t:
            if t:
                frame += 1
                if frame == len(frames): frame = 0
                next_t += int(durations[frame])
            period = int(frames[frame,0])
            gain,mode = int(frames[frame,1])&15,(int(frames[frame,1])>>4)&3
            phase = period
            first = int(frames[frame,2])
            coefficients[0],coefficients[1] = int(tables[4,first&15]),int(tables[5,first>>4])
            for j in range(1,4):
                value = int(frames[frame,2+j])
                coefficients[j*2],coefficients[j*2+1] = ((value&15)-8)*16,((value>>4)-8)*16
        ex = 0
        if period:
            phase = (phase-1)&255
            if not phase:
                phase = period
                ex = int(tables[mode,0])*gain
            else:
                lag = period-phase
                if lag < 16: ex = int(tables[mode,lag])*gain
        else:
            low = seed&1
            seed >>= 1
            if low: seed ^= 0xb8
            ex = -gain if seed&1 else gain
        for j in range(7,-1,-1):
            old,coefficient = states[j],coefficients[j]
            counts[2] += int(old == -128 and coefficient < 0)
            raw = ex-multiply(old,coefficient,nearest)
            counts[0] += int(raw < -128 or raw > 127)
            ex = base.signed(raw)
            if j < 7:
                counts[2] += int(ex == -128 and coefficient < 0)
                raw = old+multiply(ex,coefficient,nearest)
                counts[1] += int(raw < -128 or raw > 127)
                states[j+1] = base.signed(raw)
        states[0] = ex
        if tilt_shift:
            raw = ex+previous-(previous>>tilt_shift)
            counts[3] += int(raw < -128 or raw > 127)
            previous = base.signed(raw)
            ex = previous
        output[t] = (ex+128)&255
    return output,counts
