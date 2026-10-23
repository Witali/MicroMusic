"""Clip-trained consonant noise colors over the continuous-phase period model.

Color zero exactly preserves the old high-band residual. Three additional
15-tap symmetric FIRs use eight signed 4-bit values each (12 bytes total).
Each frame carries a six-bit code: two color bits and four envelope bits.
This is a PC model; payload sizes do not include an executable AVR decoder.
"""
from copy import deepcopy
import struct
import numpy as np
from scipy.signal import lfilter
from period_wave import HOP, SR, FrameSynthesis, noise_colors, packed_bytes, unpack_bytes
from period_residual import decode_residual
from joint_period import JointSynthesis


def noise_matrix(model):
    samples = model['base']['samples']
    white = np.empty(samples)
    state = 23065
    for i in range(samples):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        state &= 0xffffffff
        white[i] = (state/2147483648-1)*np.sqrt(3)
    colors = [noise_colors(samples)[12]]
    for unique in model['noise_filters']:
        taps = np.r_[unique, unique[-2::-1]].astype(float)/8
        colors.append(lfilter(taps, [1.], white))
    return np.asarray(colors)


def validate(model):
    if model['schema'] != 'period-colored-v1':
        raise ValueError('Unsupported colored-period model')
    codes = np.asarray(model['gains'], dtype=int)
    filters = np.asarray(model['noise_filters'], dtype=int)
    if (codes.shape != (len(model['base']['frames']),) or filters.shape != (3, 8) or
            np.any((codes < 0) | (codes > 63)) or np.any(abs(filters) > 7) or
            not 0 <= model['scale_u16'] <= 65535):
        raise ValueError('Invalid colored-period parameters')


def decode_colored(model):
    from period_wave import decode_model
    validate(model)
    samples = model['base']['samples']
    codes = np.asarray(model['gains'], dtype=int)
    centres = np.arange(len(codes))*HOP+HOP/2
    position = np.interp(np.arange(samples), centres, np.arange(len(codes)))
    left = np.floor(position).astype(int)
    right = np.minimum(left+1, len(codes)-1)
    weight = position-left
    colors = noise_matrix(model)
    def contribution(index):
        return colors[codes[index] >> 4, np.arange(samples)]*(codes[index] & 15)/15*model['scale_u16']/65535
    return decode_model(model['base']) + contribution(left)*(1-weight) + contribution(right)*weight


def pack_colored(model):
    validate(model)
    book = np.asarray(model['noise_filters'], dtype=int).ravel() & 15
    encoded = bytearray(struct.pack('<4sH', b'PC\x01\x00', model['scale_u16']))
    encoded.extend((book[::2] | book[1::2] << 4).astype(np.uint8).tobytes())
    encoded.extend(packed_bytes(model['base']))
    reservoir, bits = 0, 0
    for code in model['gains']:
        reservoir |= int(code) << bits
        bits += 6
        while bits >= 8:
            encoded.append(reservoir & 255)
            reservoir >>= 8
            bits -= 8
    if bits:
        encoded.append(reservoir)
    return bytes(encoded)


def unpack_colored(payload):
    if len(payload) < 284 or payload[:4] != b'PC\x01\x00':
        raise ValueError('Invalid colored-period payload')
    samples = struct.unpack('<H', payload[22:24])[0]
    count = (samples+HOP-1)//HOP
    base_size = 266+2*count
    if len(payload) != 18+base_size+(6*count+7)//8:
        raise ValueError('Truncated colored-period payload')
    book = np.frombuffer(payload[6:18], dtype=np.uint8).astype(int)
    book = np.column_stack((book & 15, book >> 4)).ravel()
    book[book >= 8] -= 16
    base = unpack_bytes(payload[18:18+base_size])
    codes, reservoir, bits = [], 0, 0
    for byte in payload[18+base_size:]:
        reservoir |= byte << bits
        bits += 8
        while bits >= 6 and len(codes) < count:
            codes.append(reservoir & 63)
            reservoir >>= 6
            bits -= 6
    model = dict(schema='period-colored-v1', base=base, scale_u16=struct.unpack('<H', payload[4:6])[0],
                 noise_filters=book.reshape(3, 8).tolist(), gains=codes)
    validate(model)
    return model


def learn_colored_model(legacy, reference, seed=23069):
    """Learn three noise envelopes from missing reference spectral power.

    Phase of this noise is deliberately synthetic. Spectral centroids are
    clustered, converted to linear-phase FIRs, windowed and quantized. All
    learned coefficients are transmitted; the decoder never reads the WAV.
    """
    output = decode_residual(legacy)
    spectra, energy = [], []
    for centre in np.arange(len(legacy['gains']))*HOP+HOP/2:
        indices = np.arange(int(centre)-64, int(centre)+64)
        valid = (indices >= 0) & (indices < len(reference))
        ref, decoded = np.zeros(128), np.zeros(128)
        ref[valid], decoded[valid] = reference[indices[valid]], output[indices[valid]]
        missing = np.maximum(abs(np.fft.rfft(ref*np.hanning(128)))**2-abs(np.fft.rfft(decoded*np.hanning(128)))**2, 0)
        total = float(missing.sum())
        spectra.append(missing/max(total, 1e-20))
        energy.append(total)
    vectors = np.asarray(spectra)[np.asarray(energy) > max(energy)*.002]
    if not len(vectors):
        vectors = np.ones((3, 65))/65
    rng, best = np.random.default_rng(seed), None
    for _ in range(8):
        centres = vectors[rng.choice(len(vectors), 3, replace=len(vectors)<3)].copy()
        for iteration in range(50):
            distances = np.sum((np.sqrt(vectors[:, None, :])-np.sqrt(centres[None, :, :]))**2, axis=2)
            labels = np.argmin(distances, axis=1)
            updated = centres.copy()
            for j in range(3):
                if np.any(labels == j):
                    updated[j] = vectors[labels == j].mean(axis=0)
            if np.max(abs(updated-centres)) < 1e-9:
                break
            centres = updated
        loss = float(np.min(distances, axis=1).sum())
        if best is None or loss < best[0]:
            best = loss, centres.copy()
    frequency = np.linspace(0, .5, 65)
    filters = []
    for power in best[1]:
        # Numerical inverse cosine transform with a seven-sample group delay.
        taps = 2*np.trapezoid(np.sqrt(power)[None, :]*np.cos(2*np.pi*(np.arange(15)[:, None]-7)*frequency), frequency, axis=1)
        taps *= np.hamming(15)
        taps = np.rint(taps/max(np.max(abs(taps)), 1e-20)*7).clip(-7, 7).astype(int)
        filters.append(taps[:8].tolist())
    return dict(schema='period-colored-v1', base=deepcopy(legacy['base']), scale_u16=legacy['scale_u16'],
                noise_filters=filters, gains=legacy['gains'].copy())


class ColoredSynthesis(JointSynthesis):
    gain_count = 64
    pack = staticmethod(pack_colored)
    decode = staticmethod(decode_colored)

    def __init__(self, model):
        validate(model)
        self.base = FrameSynthesis(model['base'])
        self.template = deepcopy(model)
        count = len(model['gains'])
        centres = np.arange(count)*HOP+HOP/2
        position = np.interp(np.arange(self.base.samples), centres, np.arange(count))
        noise = noise_matrix(model)*model['scale_u16']/65535/15
        self.residual = []
        for i, region in enumerate(self.base.slices):
            self.residual.append(noise[:, region]*np.maximum(0., 1-abs(position[region]-i)))

    def contribution(self, i, frame, gain):
        return self.base.contribution(i, frame) + self.residual[i][gain >> 4]*(gain & 15)
