"""Opt-in LPWB v1 host research stream with periodic LPX excitation.

This format is deliberately separate from LPX firmware formats. Its decoder
uses only serialized fields and the unchanged default Q0 synthesis model.
The final 320-sample packet is complete; only returned PCM is trimmed to n.
Fields belonging to the unused excitation mode canonicalize when unpacked.
"""
from __future__ import annotations

import struct
import numpy as np
from numba import njit

from lpx4 import BitReader, BitWriter
import speech_compact as compact
import speech_v4 as v4
from q0_model import coefficient_trace, synthesize, table
from wav_lpc import pack_frames


HEADER = struct.Struct('<4sBBHIHHBHHH')
MAGIC = b'LPWB'
VERSION = 1
SAMPLE_RATE = 8000
PERIOD = 32
BLOCK = 160
PACKET = 320


def _integer(value, low, high, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f'{name} must be an integer')
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f'{name} is out of range')
    return value


def _rows(values, count, width, name):
    try:
        rows = [list(row) for row in values]
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid {name}') from exc
    if len(rows) != count or any(len(row) != width for row in rows):
        raise ValueError(f'Invalid {name} dimensions')
    return rows


def validate(model):
    """Return independent, range-checked Python fields, including inactive ones."""
    try:
        n = _integer(model['n'], 1, 64000, 'sample count')
        profile = _integer(model['profile'], 4, 6, 'profile')
        if profile not in (4, 6):
            raise ValueError('Unsupported profile')
        pre = _integer(model['pre'], 0, 16384, 'pre-emphasis')
        bright = _integer(model['bright'], 0, 11469, 'brightness')
        enhanced = model['enhanced']
        if not isinstance(enhanced, (bool, np.bool_, int, np.integer)) or enhanced not in (0, 1):
            raise ValueError('Invalid enhanced flag')
        enhanced = bool(enhanced)
        initial = _integer(model['initial_phase'], 0, 65535, 'initial phase')
        seed = _integer(model['noise_seed'], 0, 65535, 'noise seed')
        packets = (n + PACKET - 1) // PACKET
        blocks = packets * 2
        book = list(model['book'])
        k = len(book)
        if k not in (1, 2, 4, 8, 16):
            raise ValueError('Dictionary size must be a power of two in 1..16')
        book = [[_integer(x, -7, 7, 'dictionary sample') for x in row]
                for row in _rows(book, k, PERIOD, 'dictionary')]
        bits = 5 if profile == 4 else 6
        spectra = [[_integer(x, 0, (1 << bits) - 1, 'spectrum') for x in row]
                   for row in _rows(model['spectra'], packets, 10, 'spectra')]
        if any(any(a >= b for a, b in zip(row, row[1:])) for row in spectra):
            raise ValueError('Unordered scalar spectrum')
        params = [[_integer(s, 0, 31, 'scale'), _integer(l, 18, 145, 'lag'),
                   _integer(g, 0, 14, 'pitch gain')]
                  for s, l, g in _rows(model['params'], blocks, 3, 'parameters')]
        if any(g & 1 for _, _, g in params):
            raise ValueError('Pitch gain must be even')
        pulses = [[_integer(p, 0, 19, 'pulse position'),
                   _integer(a, -8, 8 if profile == 4 else 7, 'pulse amplitude')]
                  for p, a in _rows(model['pulses'], blocks * 8, 2, 'pulses')]
        if profile == 4 and any(p not in v4.POSITIONS4 or a not in (-8, 8) for p, a in pulses):
            raise ValueError('Invalid profile 4 pulse')
        extras = [[_integer(p, -1, 39, 'extra position'), _integer(a, -8, 7, 'extra amplitude')]
                  for p, a in _rows(model['extras'], blocks * 4, 2, 'extras')]
        if any(a and (p < 0 or not enhanced) for p, a in extras):
            raise ValueError('Extra pulse requires a position and enhanced flag')
        codes = [_integer(x, 0, 255, 'phase code') for x in model['phase_codes']]
        modes = [_integer(x, 0, 1, 'excitation mode') for x in model['modes']]
        if len(codes) != blocks or len(modes) != blocks:
            raise ValueError('Invalid phase/mode count')
        waves = [[_integer(i, 0, k - 1, 'wave index'), _integer(g, 0, 31, 'wave gain'),
                  _integer(l, 0, 15, 'noise level')]
                 for i, g, l in _rows(model['wave_params'], blocks, 3, 'wave parameters')]
    except (KeyError, TypeError) as exc:
        raise ValueError('Incomplete period excitation model') from exc
    return dict(n=n, profile=profile, spectra=spectra, params=params, pulses=pulses,
                extras=extras, pre=pre, bright=bright, enhanced=enhanced, book=book,
                phase_codes=codes, modes=modes, wave_params=waves,
                initial_phase=initial, noise_seed=seed)


def from_compact(blob, book, initial_phase=0, noise_seed=0xACE1):
    """Start with all legacy modes from a complete speech v4 or compact v5 stream."""
    if len(blob) < 5:
        raise ValueError('Short speech stream')
    if blob[4] == 4:
        n, profile, spectra, params, pulses, pre, bright = compact.components(blob)
        extras = [(-1, 0)] * (len(spectra) * 8)
        enhanced = False
    else:
        n, profile, spectra, params, pulses, pre, bright, extras = compact.unpack(blob)
        enhanced = bool(blob[5] & 128)
    blocks = len(params)
    return validate(dict(n=n, profile=profile, spectra=spectra, params=params, pulses=pulses,
                         extras=extras, pre=pre, bright=bright, enhanced=enhanced, book=book,
                         phase_codes=[0] * blocks, modes=[0] * blocks,
                         wave_params=[(0, 0, 0)] * blocks,
                         initial_phase=initial_phase, noise_seed=noise_seed))


def _put_legacy(w, model, block):
    scale, lag, gain = model['params'][block]
    w.put(scale, 5)
    w.put(lag - 18, 7)
    w.put(gain // 2, 3)
    for chunk in range(4):
        first, second = model['pulses'][block * 8 + chunk * 2:block * 8 + chunk * 2 + 2]
        if model['profile'] == 4:
            for pos, amp in (first, second):
                w.put(int(np.flatnonzero(v4.POSITIONS4 == pos)[0]), 4)
                w.put(int(amp > 0), 1)
        else:
            combo = first[0] + 20 * second[0]
            w.put(combo & 255, 8)
            w.put(combo >> 8, 1)
            w.put(first[1] & 15, 4)
            w.put(second[1] & 15, 4)
        if model['enhanced']:
            pos, amp = model['extras'][block * 4 + chunk]
            w.put(int(amp != 0), 1)
            if amp:
                w.put(pos, 6)
                w.put(amp & 15, 4)


def pack(model):
    model = validate(model)
    k = len(model['book'])
    index_bits = k.bit_length() - 1
    w = BitWriter()
    old = None
    for packet, spectrum in enumerate(model['spectra']):
        compact.put_spectrum(w, spectrum, old, 5 if model['profile'] == 4 else 6)
        old = spectrum
        for block in (packet * 2, packet * 2 + 1):
            w.put(model['phase_codes'][block], 8)
            mode = model['modes'][block]
            w.put(mode, 1)
            if not mode:
                _put_legacy(w, model, block)
            else:
                index, gain, level = model['wave_params'][block]
                w.put(model['params'][block][0], 5)
                w.put(index, index_bits)
                w.put(gain, 5)
                w.put(level, 4)
    w.aligned()
    payload = w.get()
    if len(payload) > 65535:
        raise ValueError('Period excitation payload exceeds uint16 length')
    nibbles = np.asarray(model['book'], np.int64).ravel() & 15
    dictionary = (nibbles[::2] | (nibbles[1::2] << 4)).astype(np.uint8).tobytes()
    header = HEADER.pack(MAGIC, VERSION, model['profile'] | (128 if model['enhanced'] else 0),
                         SAMPLE_RATE, model['n'], model['pre'], model['bright'], k,
                         model['initial_phase'], model['noise_seed'], len(payload))
    return header + dictionary + payload


def unpack(blob):
    if len(blob) < HEADER.size:
        raise ValueError('Short period excitation header')
    magic, version, flags, rate, n, pre, bright, k, initial, seed, size = HEADER.unpack_from(blob)
    profile = flags & 127
    if (magic, version, rate) != (MAGIC, VERSION, SAMPLE_RATE) or profile not in (4, 6):
        raise ValueError('Unsupported period excitation header')
    if (not 1 <= n <= 64000 or pre > 16384 or bright > 11469 or
            k not in (1, 2, 4, 8, 16) or len(blob) != HEADER.size + 16 * k + size):
        raise ValueError('Invalid period excitation geometry')
    raw = np.frombuffer(blob[HEADER.size:HEADER.size + 16 * k], dtype=np.uint8)
    nibbles = np.column_stack((raw & 15, raw >> 4)).ravel().astype(np.int64)
    signed = np.where(nibbles >= 8, nibbles - 16, nibbles)
    if np.any(signed == -8):
        raise ValueError('Invalid dictionary nibble')
    model = dict(n=n, profile=profile, spectra=[], params=[], pulses=[], extras=[],
                 pre=pre, bright=bright, enhanced=bool(flags & 128), book=signed.reshape(k, PERIOD).tolist(),
                 phase_codes=[], modes=[], wave_params=[], initial_phase=initial, noise_seed=seed)
    r = BitReader(blob[HEADER.size + 16 * k:])
    old = None
    for _ in range((n + PACKET - 1) // PACKET):
        spectrum = compact.get_spectrum(r, old, 5 if profile == 4 else 6)
        old = spectrum
        model['spectra'].append(spectrum)
        for _ in range(2):
            model['phase_codes'].append(r.get(8))
            mode = r.get(1)
            model['modes'].append(mode)
            if mode:
                model['params'].append([r.get(5), 18, 0])
                model['wave_params'].append([r.get(k.bit_length() - 1), r.get(5), r.get(4)])
                model['pulses'].extend([[0, -8 if profile == 4 else 0] for _ in range(8)])
                model['extras'].extend([[-1, 0] for _ in range(4)])
                continue
            model['params'].append([r.get(5), r.get(7) + 18, r.get(3) * 2])
            model['wave_params'].append([0, 0, 0])
            for _ in range(4):
                if profile == 4:
                    for _ in range(2):
                        model['pulses'].append([int(v4.POSITIONS4[r.get(4)]), 8 if r.get(1) else -8])
                else:
                    combo = r.get(8) | (r.get(1) << 8)
                    if combo >= 400:
                        raise ValueError('Invalid radix20 position pair')
                    for pos in (combo % 20, combo // 20):
                        amp = r.get(4)
                        model['pulses'].append([pos, amp if amp < 8 else amp - 16])
                pos, amp = -1, 0
                if model['enhanced'] and r.get(1):
                    pos, amp = r.get(6), r.get(4)
                    amp = amp if amp < 8 else amp - 16
                    if pos >= 40 or not amp:
                        raise ValueError('Invalid extra innovation')
                model['extras'].append([pos, amp])
    if r.o != len(r.data) or r.acc:
        raise ValueError('Unexpected period excitation trailing data')
    return validate(model)


def coefficients(model):
    """Return the unchanged Q12 coefficient trace for the full padded packets."""
    model = validate(model)
    shift = 5 if model['profile'] == 4 else 4
    vectors = [[(v << shift) + (1 << (shift - 1)) for v in spectrum]
               for spectrum in model['spectra'] for _ in range(2)]
    return coefficient_trace(pack_frames(vectors), len(vectors) * BLOCK)


@njit(cache=True)
def _oscillators(codes, initial, seed):
    samples = len(codes) * BLOCK
    phases = np.empty(samples, np.uint16)
    noise = np.empty(samples, np.int16)
    phase = initial
    previous = 0
    for j in range(samples):
        phases[j] = phase
        phase = (phase + int(codes[j // BLOCK]) * 32) & 65535
        for _ in range(8):
            carry = seed & 1
            seed >>= 1
            if carry:
                seed ^= 0xB400
        current = (seed & 255) - 128
        noise[j] = current - previous
        previous = current
    return phases, noise


def oscillators(model):
    """Advance phase and deterministic differentiated noise in every mode."""
    model = validate(model)
    return _oscillators(np.asarray(model['phase_codes'], np.int64),
                        model['initial_phase'], model['noise_seed'])


@njit(cache=True)
def book_sample(book, index, gain, noise_level, phase, noise):
    """Unclipped integer book/noise sum, shared with the offline encoder."""
    at = int(phase) >> 11
    fraction = (int(phase) >> 7) & 15
    a = int(book[index, at])
    b = int(book[index, (at + 1) & 31])
    shape = a * 16 + (b - a) * fraction
    return ((shape * gain + 64) >> 7) + ((int(noise) * noise_level + 64) >> 7)


@njit(cache=True)
def _render_q(book, params, pulses, extras, modes, waves, phases, noise):
    q = np.empty(len(phases), np.int64)
    for j in range(len(q)):
        block = j // BLOCK
        local = j % BLOCK
        if modes[block]:
            index, gain, level = waves[block]
            value = book_sample(book, index, gain, level, phases[j], noise[j])
            if block and modes[block - 1] and local < 16:
                index, gain, level = waves[block - 1]
                old = book_sample(book, index, gain, level, phases[j], noise[j])
                value = (old * (16 - local) + value * local + 8) >> 4
        else:
            _, lag, gain = params[block]
            old = q[j - lag] if j >= lag else 0
            value = min(31, max(-32, (gain * old + 8) >> 4))
            pos, amp = pulses[j // 20]
            ep, ea = extras[j // 40]
            value += (amp if j % 20 == pos else 0) + (ea if j % 40 == ep else 0)
        q[j] = min(31, max(-32, value))
    return q


def render_q(model):
    """Return all padded excitation; legacy prediction sees actual mixed history."""
    model = validate(model)
    phases, noise = _oscillators(np.asarray(model['phase_codes'], np.int64),
                                model['initial_phase'], model['noise_seed'])
    return _render_q(np.asarray(model['book'], np.int64), np.asarray(model['params'], np.int64),
                     np.asarray(model['pulses'], np.int64), np.asarray(model['extras'], np.int64),
                     np.asarray(model['modes'], np.int64), np.asarray(model['wave_params'], np.int64),
                     phases, noise)


def decode_model(blob):
    model = unpack(blob)
    q = render_q(model)[:model['n']]
    scales = np.repeat(np.asarray(model['params'], np.int64)[:, 0] * 8, 2)
    return synthesize(q, scales, coefficients(model)[:model['n']], table('scale_table.inc'),
                      model['pre'], model['bright'])
