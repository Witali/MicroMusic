"""Explicit version8/mode15 speech stream and exact v5/P6 reference bridge.

The syntax is identical to the earlier S15 experiment. Its name denotes one
innovation per80 samples, not a promised file rate. No firmware arithmetic,
source pitch, output level or sample-rate conversion occurs in this adapter.
"""
from __future__ import annotations

import struct

from lpx4 import HEADER, BitReader, BitWriter
import speech_compact as compact

POSITIONS = tuple(code + ((code + 2) >> 2) for code in range(64))


def pack(n, spectra, params, pulses, pre=13926, bright=0):
    frames = (n + 319) // 320
    if not 1 <= n <= 64000 or not 0 <= pre <= 16384 or not 0 <= bright <= 11469:
        raise ValueError('Invalid count or filter')
    if len(spectra) != frames or len(params) != frames or len(pulses) != frames * 4:
        raise ValueError('Incomplete final sparse80 packet')
    writer = BitWriter()
    previous = None
    for frame, vector in enumerate(spectra):
        if (len(vector) != 10 or any(not 0 <= v < 64 for v in vector)
                or any(a >= b for a, b in zip(vector, vector[1:]))):
            raise ValueError('Invalid ordered six-bit spectrum')
        compact.put_spectrum(writer, list(vector), previous, 6)
        previous = list(vector)
        scale, lag, gain = map(int, params[frame])
        if not 0 <= scale < 32 or not 18 <= lag <= 145 or gain not in range(0, 15, 2):
            raise ValueError('Invalid sparse80 parameters')
        writer.put(scale, 5)
        writer.put(lag - 18, 7)
        writer.put(gain // 2, 3)
        for position, amplitude in pulses[frame*4:frame*4+4]:
            if position not in POSITIONS or amplitude not in (-8, 7):
                raise ValueError('Invalid sparse80 innovation')
            writer.put(POSITIONS.index(int(position)), 6)
            writer.put(int(amplitude > 0), 1)
    writer.aligned()
    payload = writer.get()
    return struct.pack(HEADER, b'L4HY', 8, 15, 8000, n, pre, bright, 320, 320) + struct.pack('<H', len(payload)) + payload


def unpack(blob):
    if len(blob) < 22:
        raise ValueError('Short sparse80 header')
    magic, version, mode, rate, n, pre, bright, frame, block = struct.unpack(HEADER, blob[:20])
    if (magic, version, mode, rate, frame, block) != (b'L4HY', 8, 15, 8000, 320, 320):
        raise ValueError('Unsupported sparse80 syntax')
    if len(blob) != 22 + int.from_bytes(blob[20:22], 'little') or not 1 <= n <= 64000:
        raise ValueError('Invalid sparse80 length')
    reader = BitReader(blob[22:])
    spectra, parameters, pulses = [], [], []
    previous = None
    for _ in range((n + 319) // 320):
        vector = compact.get_spectrum(reader, previous, 6)
        spectra.append(vector)
        previous = vector
        parameters.append((reader.get(5), reader.get(7) + 18, reader.get(3) * 2))
        for _ in range(4):
            pulses.append((POSITIONS[reader.get(6)], 7 if reader.get(1) else -8))
    if reader.o != len(reader.data) or reader.acc:
        raise ValueError('Unexpected sparse80 tail')
    fields = n, spectra, parameters, pulses, pre, bright
    # Multiple spectrum encodings can be legal; validate the decoded fields
    # without requiring the shortest serializer to reproduce those bytes.
    pack(*fields)
    return fields


def expand(blob):
    n, spectra, parameters, pulses, pre, bright = unpack(blob)
    expanded = [(0, 0)] * (len(spectra) * 16)
    for group, (position, amplitude) in enumerate(pulses):
        expanded[group * 4 + position // 20] = (position % 20, amplitude)
    return compact.pack(n, 6, spectra, [tuple(p) for p in parameters for _ in range(2)],
                        expanded, pre, bright)[0]


def decode_model(blob):
    return compact.decode_model(expand(blob))
