"""Bounded PC experiment: four-bit high-band noise envelope over period-wave v2.

The extension is source-independent at decode time. Its six-byte header and
packed gains are counted, but neither decoder has been implemented on AVR.
"""
import struct
from copy import deepcopy
import numpy as np
from scipy.signal import butter, sosfilt
from pystoi import stoi
from period_wave import SR, HOP, decode_model, noise_colors, packed_bytes, unpack_bytes


def decode_residual(model):
    if model['schema'] != 'period-residual-v1':
        raise ValueError('Unsupported residual extension')
    base = model['base']
    gains = np.asarray(model['gains'], dtype=int)
    if len(gains) != len(base['frames']) or np.any((gains < 0) | (gains > 15)) or not 0 <= model['scale_u16'] <= 65535:
        raise ValueError('Invalid residual envelope')
    centres = np.arange(len(gains))*HOP+HOP/2
    envelope = np.interp(np.arange(base['samples']), centres, gains)/15*model['scale_u16']/65535
    return decode_model(base) + noise_colors(base['samples'])[12]*envelope


def pack_residual(model):
    decode_residual(model)
    gains = np.asarray(model['gains'], dtype=np.uint8)
    if len(gains) % 2:
        gains = np.r_[gains, np.uint8(0)]
    return struct.pack('<4sH', b'PR\x01\x00', model['scale_u16']) + packed_bytes(model['base']) + (gains[::2] | gains[1::2] << 4).tobytes()


def unpack_residual(payload):
    if len(payload) < 272 or payload[:4] != b'PR\x01\x00':
        raise ValueError('Invalid residual payload')
    samples = struct.unpack('<H', payload[10:12])[0]
    count = (samples+HOP-1)//HOP
    size = 266+2*count
    if len(payload) != 6+size+(count+1)//2:
        raise ValueError('Truncated residual payload')
    base = unpack_bytes(payload[6:6+size])
    packed = np.frombuffer(payload[6+size:], dtype=np.uint8).astype(int)
    gains = np.column_stack((packed & 15, packed >> 4)).ravel()[:count]
    return dict(schema='period-residual-v1', base=base, scale_u16=struct.unpack('<H', payload[4:6])[0], gains=gains.tolist())


def fit_residual(base, objective, proposals=3000, seed=23067):
    original = decode_model(base)
    highpass = butter(2, 1800, fs=SR, btype='highpass', output='sos')
    high_ref, high_out = sosfilt(highpass, objective.reference), sosfilt(highpass, original)
    targets = []
    for start in range(0, base['samples'], HOP):
        a, b = high_ref[start:start+HOP], high_out[start:start+HOP]
        targets.append(np.sqrt(max(0., np.mean(a*a)-np.mean(b*b))))
    scale = max(1, int(np.rint(min(1., max(targets)*1.5)*65535)))
    model = dict(schema='period-residual-v1', base=deepcopy(base), scale_u16=scale,
                 gains=np.rint(np.array(targets)/(scale/65535)*15).clip(0, 15).astype(int).tolist())
    def score(audio):
        return objective.spectrum(audio)['loss']+2*(1-float(stoi(objective.reference, audio, SR)))
    baseline = energy = score(original)
    audio = decode_residual(model)
    if score(audio) < energy:
        energy = score(audio)
    else:
        audio = original.copy()
        model['gains'] = [0]*len(targets)
    noise = noise_colors(base['samples'])[12]*scale/65535/15
    centres = np.arange(len(targets))*HOP+HOP/2
    position = np.interp(np.arange(base['samples']), centres, np.arange(len(targets)))
    bases, regions = [], []
    for i in range(len(targets)):
        weight = np.maximum(0., 1-abs(position-i))
        support = np.flatnonzero(weight > 0)
        region = slice(int(support[0]), int(support[-1])+1)
        regions.append(region)
        bases.append(noise[region]*weight[region])
    rng = np.random.default_rng(seed)
    improvements = 0
    for step in range(proposals):
        i = int(rng.integers(len(targets)))
        gain = int(rng.integers(16))
        if gain == model['gains'][i]:
            continue
        candidate = audio.copy()
        candidate[regions[i]] += bases[i]*(gain-model['gains'][i])
        value = score(candidate)
        if value < energy:
            audio, energy, model['gains'][i] = candidate, value, gain
            improvements += 1
    if not np.allclose(audio, decode_residual(model), rtol=0, atol=1e-11):
        raise AssertionError('Residual search differs from independent decoder')
    return model, dict(seed=seed, proposals=proposals, improvements=improvements,
                       objective='spectral_loss + 2 * (1 - STOI)', initial_energy=baseline, final_energy=energy)
