"""Portable integer specification for a compact period/noise decoder.

All synthesis is integer. Fixed-point conventions are part of the versioned
model, shared by PC output and AVR. This code is the independent AVR oracle.
"""
from copy import deepcopy
import struct
import numpy as np
from numba import njit

SR = 7500
HOP = 64


def from_colored(source, phase_bits=4):
    if source['schema'] != 'period-colored-v1':
        raise ValueError('Expected a colored-period model')
    frames = []
    for frame, residual in zip(source['base']['frames'], source['gains']):
        pitch, index, gain, voiced = frame
        frames.append([pitch, index | gain << 4 | voiced << 7, residual])
    return dict(schema='period-fixed-v1', sample_rate=SR, samples=source['base']['samples'],
                hop=HOP, phase_bits=phase_bits, initial_phase_u16=source['base']['initial_phase_u16'],
                noise_seed_u16=0xace1, codebook=deepcopy(source['base']['codebook']),
                noise_filters=deepcopy(source['noise_filters']), frames=frames)


def validate(model):
    if (model['schema'] != 'period-fixed-v1' or model['sample_rate'] != SR or model['hop'] != HOP or
            model['phase_bits'] not in (4, 5, 6) or model.get('dc_block_shift', 0) not in (0, 5, 6, 7) or not 1 <= model['samples'] <= 65535 or
            not 0 <= model['initial_phase_u16'] <= 65535 or not 1 <= model['noise_seed_u16'] <= 65535):
        raise ValueError('Unsupported fixed-period model')
    frames = np.asarray(model['frames'], dtype=np.int64)
    book = np.asarray(model['codebook'], dtype=np.int64)
    filters = np.asarray(model['noise_filters'], dtype=np.int64)
    if (frames.shape != ((model['samples']+HOP-1)//HOP, 3) or book.shape != (16, 32) or
            filters.shape != (3, 8) or np.any(abs(book)>7) or np.any(abs(filters)>7) or
            np.any((frames < 0) | (frames > [255, 255, 63])) or
            np.any(2*np.abs(filters[:, :7]).sum(axis=1)+np.abs(filters[:, 7]) > 17)):
        raise ValueError('Invalid fixed-period parameters')
    return frames, book, filters


@njit(cache=True)
def gain_sample(value, gain):
    if gain == 0:
        return 0
    if gain == 7:
        return value
    if gain == 6:
        return (3*value+2) >> 2
    shift = 6-gain
    return (value+(1 << (shift-1))) >> shift


@njit(cache=True)
def integer_noise(samples, seed, filters):
    colors = np.empty((4, samples), np.int16)
    history = np.zeros(15, np.int16)
    for n in range(samples):
        for _ in range(8):
            carry = seed & 1
            seed >>= 1
            if carry:
                seed ^= 0xb400
        for k in range(14, 0, -1):
            history[k] = history[k-1]
        history[0] = (seed & 255)-128
        colors[0, n] = history[0]-history[1]
        for color in range(3):
            total = 0
            for k in range(15):
                total += int(history[k])*int(filters[color, k if k<8 else 14-k])
            colors[color+1, n] = total
    return colors


@njit(cache=True)
def frame_sample(header, residual, phase, book, noise, n, phase_bits):
    gain = (header >> 4) & 7
    sample = 0
    if gain:
        if header & 128:
            word = header & 15
            index = phase >> 11
            fraction = (phase >> (11-phase_bits)) & ((1 << phase_bits)-1)
            a, b = int(book[word, index]), int(book[word, (index+1) & 31])
            product = (b-a)*fraction
            if phase_bits > 4:
                product = (product+(1 << (phase_bits-5))) >> (phase_bits-4)
            sample = gain_sample(a*16+product, gain)
        else:
            # Three active noisy source frames need only a high-band excitation.
            # Their exact gain is retuned against this decoder, not hand edited.
            sample = gain_sample(int(noise[0, n]), gain)
    level = residual & 15
    if level:
        color = residual >> 4
        total = int(noise[color, n])*level
        if color == 0:
            sample += (total+32) >> 6
        else:
            # The early shift keeps every following intermediate in int16.
            sample += (3*(total >> 2)+128) >> 8
    return max(-128, min(127, sample))


@njit(cache=True)
def synthesize(frames, book, noise, samples, initial_phase, phase_bits):
    out = np.empty(samples, np.uint8)
    phase = initial_phase
    for n in range(samples):
        left = max(0, (n-32)//64)
        right = min(len(frames)-1, left+1) if n >= 32 else 0
        blend = ((n-32) & 63) if n >= 32 else 0
        first = frame_sample(int(frames[left, 1]), int(frames[left, 2]), phase, book, noise, n, phase_bits)
        second = frame_sample(int(frames[right, 1]), int(frames[right, 2]), phase, book, noise, n, phase_bits)
        sample = first+(((second-first)*blend+32) >> 6)
        out[n] = sample+128
        phase = (phase+(int(frames[n//64, 0]) << 5)) & 65535
    return out


def decode_fixed(model):
    frames, book, filters = validate(model)
    noise = integer_noise(model['samples'], model['noise_seed_u16'], filters)
    pcm = synthesize(frames, book, noise, model['samples'], model['initial_phase_u16'], model['phase_bits'])
    if model.get('dc_block_shift', 0):
        from dc_blocker import block_dc
        pcm = block_dc(pcm, model['dc_block_shift'])[0]
    return pcm


def _compact_model(model):
    frames, _, _ = validate(model)
    base = dict(schema='period-wave-v2', sample_rate=SR, samples=model['samples'], hop=HOP,
                initial_phase_u16=model['initial_phase_u16'], scale_u16=65535,
                codebook=model['codebook'], frames=[
                    [int(p), int(h)&15, (int(h)>>4)&7, int(h)>>7] for p, h, _ in frames])
    return dict(schema='period-colored-v1', base=base, scale_u16=65535,
                noise_filters=model['noise_filters'], gains=frames[:, 2].tolist())


def pack_fixed(model):
    """Portable lossless integer payload; zero-amplitude fields canonicalize."""
    from compact_period import pack_compact
    header = struct.pack('<4sHHHBB', b'PF\x01\x00', model['samples'],
                         model['initial_phase_u16'], model['noise_seed_u16'],
                         model['phase_bits'], model.get('dc_block_shift', 0))
    return header+pack_compact(_compact_model(model))[13:]


def unpack_fixed(payload):
    from compact_period import unpack_compact
    if len(payload) < 280:
        raise ValueError('Truncated fixed-period payload')
    magic, samples, phase, seed, bits, dc = struct.unpack('<4sHHHBB', payload[:12])
    if magic != b'PF\x01\x00' or dc not in (0, 5, 6, 7):
        raise ValueError('Invalid fixed-period header')
    stub = struct.pack('<4sBHHHH', b'PX\x01\x00', 1, samples, phase, 65535, 65535)
    model = from_colored(unpack_compact(stub+payload[12:]), bits)
    model['noise_seed_u16'] = seed
    if dc:
        model['dc_block_shift'] = dc
    validate(model)
    return model


def avr_features(model):
    frames, _, filters = validate(model)
    fir = bool(np.any(((frames[:, 2] & 15) != 0) & ((frames[:, 2] >> 4) != 0)))
    single = fir and bool(np.all(filters == filters[0]))
    unvoiced = bool(np.any(((frames[:, 1] & 112) != 0) & ((frames[:, 1] & 128) == 0)))
    active_words = frames[((frames[:, 1] & 112) != 0) & ((frames[:, 1] & 128) != 0), 1] & 15
    wave_bytes = 16*(int(active_words.max())+1) if len(active_words) else 16
    return dict(ENABLE_FIR=int(fir), ENABLE_UNVOICED=int(unvoiced), SINGLE_FIR=int(single),
                FIR_BYTES=8 if single else 24 if fir else 0, HISTORY_LENGTH=16 if fir else 2,
                WAVE_BYTES=wave_bytes)


def pack_avr_data(model, *, specialize=False):
    """Headerless AVR tables: packed waves, padded full FIRs, field stream."""
    payload = pack_fixed(model)[12:]
    # Bias taps by eight, as in the older Mini-LPC parameter loader. This lets
    # AVR unpack a nibble with ANDI instead of four arithmetic shifts. The
    # constant bias is removed once after phase interpolation.
    wave = (np.asarray(model['codebook'], dtype=int).ravel()+8).astype(np.uint8)
    packed_wave = (wave[::2] | wave[1::2] << 4).tobytes()
    filters = np.asarray(model['noise_filters'], dtype=int)
    full = np.concatenate((filters, filters[:, -2::-1], np.zeros((3, 1), int)), axis=1).ravel() & 15
    fir = (full[::2] | full[1::2] << 4).astype(np.uint8).tobytes()
    if specialize:
        features = avr_features(model)
        fir = fir[:features['FIR_BYTES']]
        packed_wave = packed_wave[:features['WAVE_BYTES']]
    return packed_wave+fir+payload[268:]
