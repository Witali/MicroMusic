"""Eight selectable Q3 excitation forms, retaining all sixteen gain levels.

Selector bit 2 occupies bit 2 of an extended duration header. Lower selectors
retain the old byte stream exactly. Higher selectors force that header only
when it was not already needed. Arithmetic/phase/EOF remain the frozen Q3 rules.
"""
import numpy as np
from numba import njit
from q3_pulsebook import signed, multiply
from q3_short_eeprom import encode_book as encode_four, decode_book as decode_four, code_bytes as four_code_bytes

SCHEMA = 'hq4-q3-pulsebook8-v1'


def validate_frames(frames, durations):
    f, d = np.asarray(frames), np.asarray(durations)
    if (f.ndim != 2 or f.shape[1] != 6 or not len(f) or f.dtype.kind not in 'iu'
            or d.dtype.kind not in 'iu' or d.shape != (len(f),)
            or np.any(f < 0) or np.any(f > 255) or np.any(f[:,0] > 126)
            or np.any(f[:,1] > 127) or not np.all(np.isin(d, [64,128,192,256]))
            or np.any((f[:,2:] & 15) == 0) or np.any((f[:,2:] >> 4) == 0)):
        raise ValueError('Invalid eight-form Q3 frames/durations')
    return f, d


def pack_stream(frames, durations):
    f, d = validate_frames(frames, durations)
    out, old = bytearray(), None
    for frame, duration in zip(f, d):
        pitch, header, duration = int(frame[0]), int(frame[1]), int(duration)
        upper = (header >> 6) & 1
        if pitch <= 63 and duration != 192 and not upper:
            out.append((duration & 192)|pitch)
        else:
            out.extend((192|((duration//64)&3)|(upper << 2), pitch))
        k = list(map(int, frame[2:]))
        kind = (0 if old is None or (k[:2] != old[:2] and k[2:] != old[2:])
                else 1 if k == old else 2 if k[:2] != old[:2] else 3)
        out.append((kind << 6)|(header & 63))
        if kind == 0: out.extend(k)
        elif kind == 2: out.extend(k[:2])
        elif kind == 3: out.extend(k[2:])
        old = k
    return bytes(out)


def unpack_stream(payload):
    payload, offset, frames, durations = bytes(payload), 0, [], []
    coefficients = [0]*4
    def byte():
        nonlocal offset
        if offset == len(payload):
            raise ValueError('Truncated eight-form speech packet')
        value = payload[offset]
        offset += 1
        return value
    while offset < len(payload):
        header, upper = byte(), 0
        if header == 255:
            raise ValueError('Input must omit EOF and trailing bytes')
        if header & 192 == 192:
            if header & 56:
                raise ValueError('Unknown extended duration header bits')
            duration, upper, pitch = (header & 3)*64 or 256, (header & 4) << 4, byte()
        else:
            duration, pitch = (header & 192) or 256, header & 63
        spectral = byte()
        kind = spectral >> 6
        if not frames and kind != 0:
            raise ValueError('First frame must initialize every coefficient')
        if kind == 0: coefficients = [byte() for _ in range(4)]
        elif kind == 2: coefficients[:2] = [byte(), byte()]
        elif kind == 3: coefficients[2:] = [byte(), byte()]
        frames.append([pitch, (spectral & 63)|upper, *coefficients])
        durations.append(duration)
    f, d = np.asarray(frames, np.int64), np.asarray(durations, np.int64)
    validate_frames(f, d)
    return f.astype(np.uint8), d.astype(np.uint16)


def validate(frames, durations, book, samples=None, stream_budget=None):
    f, d = validate_frames(frames, durations)
    b = np.asarray(book)
    if b.shape != (8,16) or b.dtype.kind not in 'iu' or np.any(b < -7) or np.any(b > 7):
        raise ValueError('Eight excitation forms must be 8x16 integers in -7..7')
    if samples is not None and int(d.sum()) != samples:
        raise ValueError('Full reference duration must be preserved')
    payload = pack_stream(f, d)
    if stream_budget is not None and len(payload) > stream_budget:
        raise ValueError('Eight-form stream exceeds the measured budget')
    return payload


def encode_book(book, width, packing):
    book = np.asarray(book)
    if book.shape != (8,16):
        raise ValueError('Eight excitation rows are required')
    data = encode_four(book[:4], width, packing)+encode_four(book[4:], width, packing)
    if len(data) > 64:
        raise ValueError('Eight-form table exceeds the entire EEPROM')
    return data


def decode_book(data, width, packing):
    half = (4 if packing == 'raw' else 2)*width
    if len(data) != half*2 or len(data) > 64:
        raise ValueError('Incorrect eight-form table size')
    return np.vstack((decode_four(data[:half],width,packing), decode_four(data[half:],width,packing)))


def storage(book, payload, width, packing, prefix=None):
    encoded = encode_book(book,width,packing)
    maximum = min(64-len(encoded),len(payload))
    prefix = maximum if prefix is None else prefix
    if isinstance(prefix,bool) or not isinstance(prefix,int) or not 0 <= prefix <= maximum:
        raise ValueError('Invalid EEPROM speech prefix')
    eeprom = encoded+bytes(payload[:prefix])
    stride = width if packing == 'raw' else width//2
    code = four_code_bytes(width,packing,prefix)+10+2*(stride.bit_length()-1)
    return dict(width=width,packing=packing,book_bytes=len(encoded),prefix_bytes=prefix,
        prefix_start=len(encoded),prefix_end=len(encoded)+prefix,
        eeprom=eeprom+b'\xff'*(64-len(eeprom)),flash_suffix=bytes(payload[prefix:]),
        code_bytes=code,maximum_stream_bytes=1024-code-1+prefix)


def canonicalize_selectors(frames,book):
    """Prefer an identical lower row; silent/noise frames need no form index.

    This recoding preserves excitation, including phase and LFSR clock rules.
    It frees expensive upper-selector headers and leaves unused slots trainable.
    """
    f=np.asarray(frames).copy();b=np.asarray(book)
    validate_frames(f,np.full(len(f),64,np.uint16))
    if b.shape!=(8,16):raise ValueError('Eight excitation rows are required')
    mapping=np.array([next(j for j in range(i+1) if np.array_equal(b[i],b[j])) for i in range(8)],np.uint8)
    modes=mapping[f[:,1]>>4]
    modes[(f[:,0]==0)|((f[:,1]&15)==0)]=0
    f[:,1]=(f[:,1]&15)|(modes<<4)
    return f


@njit(cache=True)
def render(frames, durations, pulsebook, tilt_shift=1, nearest=False):
    output = np.empty(int(durations.sum()),np.uint8)
    states, coefficients = np.zeros(8,np.int32),np.zeros(8,np.int32)
    counts = np.zeros(4,np.int64)
    seed, phase, frame, next_t = 0xa7,1,0,int(durations[0])-1
    period = gain = mode = previous = 0
    for t in range(len(output)):
        if t == 0 or t == next_t:
            if t:
                frame += 1
                if frame == len(frames): frame = 0
                next_t += int(durations[frame])
            period = int(frames[frame,0])
            gain, mode = int(frames[frame,1]) & 15,(int(frames[frame,1]) >> 4) & 7
            phase = period
            for j in range(4):
                value = int(frames[frame,2+j])
                coefficients[j*2],coefficients[j*2+1] = (value & 15)-8,(value >> 4)-8
        ex = 0
        if period:
            phase = (phase-1)&255
            if not phase:
                phase = period
                ex = int(pulsebook[mode,0])*gain
            else:
                lag = period-phase
                if lag < 16: ex = int(pulsebook[mode,lag])*gain
        else:
            low = seed & 1
            seed >>= 1
            if low: seed ^= 0xb8
            ex = -gain if seed & 1 else gain
        for j in range(7,-1,-1):
            old, coefficient = states[j],coefficients[j]
            counts[2] += int(old == -128 and coefficient < 0)
            raw = ex-multiply(old,coefficient,nearest)
            counts[0] += int(raw < -128 or raw > 127)
            ex = signed(raw)
            if j < 7:
                counts[2] += int(ex == -128 and coefficient < 0)
                raw = old+multiply(ex,coefficient,nearest)
                counts[1] += int(raw < -128 or raw > 127)
                states[j+1] = signed(raw)
        states[0] = ex
        if tilt_shift:
            raw = ex+previous-(previous >> tilt_shift)
            counts[3] += int(raw < -128 or raw > 127)
            previous = signed(raw)
            ex = previous
        output[t] = (ex+128)&255
    return output, counts
