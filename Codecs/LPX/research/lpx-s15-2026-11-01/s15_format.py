"""Experimental LPX-S15 version8. Expansion is a reference, not a size claim."""
from pathlib import Path
import struct
import sys

ACTIVE = Path(__file__).resolve().parents[2] / '01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(ACTIVE / 'tools'))
from lpx4 import HEADER, BitReader, BitWriter
import speech_compact as v5

VERSION = 8
MODE = 15
RATE = 8000
FRAME = 320
POSITIONS = tuple(code + ((code + 2) >> 2) for code in range(64))


def validate(n, spectra, params, pulses, pre, bright):
    frames = (n + 319) // 320
    if not 1 <= n <= 64000 or not 0 <= pre <= 16384 or not 0 <= bright <= 11469:
        raise ValueError('Invalid count or filter')
    if len(spectra) != frames or len(params) != frames or len(pulses) != frames * 4:
        raise ValueError('Incomplete stored final packet')
    for vec in spectra:
        if len(vec) != 10 or any(not 0 <= v < 64 for v in vec) or any(a >= b for a, b in zip(vec, vec[1:])):
            raise ValueError('Invalid ordered6-bit spectrum')
    for scale, lag, gain in params:
        if not 0 <= scale < 32 or not 18 <= lag <= 145 or not 0 <= gain <= 14 or gain & 1:
            raise ValueError('Invalid320-sample parameters')
    for pos, amp in pulses:
        if pos not in POSITIONS or amp not in (-8, 7):
            raise ValueError('Invalid80-sample pulse')


def pack(n, spectra, params, pulses, pre=13926, bright=0):
    validate(n, spectra, params, pulses, pre, bright)
    w = BitWriter()
    old = None
    spectrum_bits = 0
    modes = dict(gap=0, delta=0, repeat=0)
    for fi, vec in enumerate(spectra):
        before = w.total
        mode = v5.put_spectrum(w, list(vec), old, 6)
        spectrum_bits += w.total - before
        modes[mode] += 1
        old = list(vec)
        scale, lag, gain = map(int, params[fi])
        w.put(scale, 5)
        w.put(lag - 18, 7)
        w.put(gain // 2, 3)
        for pos, amp in pulses[fi*4:fi*4+4]:
            w.put(POSITIONS.index(int(pos)), 6)
            w.put(int(amp > 0), 1)
    bits = w.total
    w.aligned()
    payload = w.get()
    header = struct.pack(HEADER, b'L4HY', VERSION, MODE, RATE, n, pre, bright, FRAME, FRAME)
    blob = header + struct.pack('<H', len(payload)) + payload
    return blob, dict(file_bytes=len(blob), payload_bits=bits, spectrum_bits=spectrum_bits,
                      fixed_parameter_bits=len(spectra)*15, fixed_pulse_bits=len(pulses)*7,
                      padding_bits=len(payload)*8-bits, spectrum_modes=modes)


def unpack(blob):
    if len(blob) < 22:
        raise ValueError('Short S15 header')
    magic, version, mode, rate, n, pre, bright, frame, block = struct.unpack(HEADER, blob[:20])
    if (magic, version, mode, rate, frame, block) != (b'L4HY', VERSION, MODE, RATE, FRAME, FRAME):
        raise ValueError('Unsupported S15 header')
    if not 1 <= n <= 64000 or len(blob) != 22 + int.from_bytes(blob[20:22], 'little'):
        raise ValueError('Invalid S15 length')
    r = BitReader(blob[22:])
    spectra, params, pulses = [], [], []
    old = None
    for _ in range((n+319)//320):
        vec = v5.get_spectrum(r, old, 6)
        spectra.append(vec)
        old = vec
        params.append((r.get(5), r.get(7)+18, r.get(3)*2))
        for _ in range(4):
            pulses.append((POSITIONS[r.get(6)], 7 if r.get(1) else -8))
    if r.o != len(r.data) or r.acc:
        raise ValueError('Unexpected S15 trailing bytes or bits')
    validate(n, spectra, params, pulses, pre, bright)
    return n, spectra, params, pulses, pre, bright


def expand(blob):
    """Exact ordinary v5/P6 expansion, with no sample-rate/pitch conversion."""
    n, spectra, params, pulses, pre, bright = unpack(blob)
    expanded_params = [tuple(p) for p in params for _ in range(2)]
    expanded_pulses = [(0, 0)] * (len(spectra)*16)
    for group, (pos, amp) in enumerate(pulses):
        expanded_pulses[group*4 + pos//20] = (pos % 20, amp)
    return v5.pack(n, 6, spectra, expanded_params, expanded_pulses, pre, bright)[0]


def decode_model(blob):
    return v5.decode_model(expand(blob))
