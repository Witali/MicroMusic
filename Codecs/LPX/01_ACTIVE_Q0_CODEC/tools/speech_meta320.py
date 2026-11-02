"""Explicit version9/mode3: one metadata tuple and16 P4 pulses per320 samples.

Spectrum coding and synthesis are unchanged. Expansion repeats the metadata
tuple into the two halves of an ordinary v5/P4 reference stream. The expanded
file is an arithmetic oracle, never the advertised compressed byte count.
"""
from __future__ import annotations

import struct

from lpx4 import HEADER, BitReader, BitWriter
import speech_compact as compact
from speech_v4 import POSITIONS4

POSITIONS = tuple(map(int, POSITIONS4))


def pack(n, spectra, params, pulses, pre=13926, bright=0):
    if not 1 <= n <= 64000 or not 0 <= pre <= 16384 or not 0 <= bright <= 11469:
        raise ValueError('Invalid meta320 count or header filters')
    frames = (n+319)//320
    if len(spectra) != frames or len(params) != frames or len(pulses) != frames*16:
        raise ValueError('Incomplete final meta320 packet')
    writer, previous = BitWriter(), None
    for frame, vector in enumerate(spectra):
        if (len(vector) != 10 or any(not 0 <= value < 32 for value in vector)
                or any(first >= second for first, second in zip(vector, vector[1:]))):
            raise ValueError('Invalid ordered five-bit spectrum')
        compact.put_spectrum(writer, list(vector), previous, 5)
        previous = list(vector)
        scale, lag, gain = map(int, params[frame])
        if not 0 <= scale < 32 or not 18 <= lag <= 145 or gain not in range(0, 15, 2):
            raise ValueError('Invalid meta320 tuple')
        writer.put(scale, 5)
        writer.put(lag-18, 7)
        writer.put(gain//2, 3)
        for position, amplitude in pulses[frame*16:(frame+1)*16]:
            if position not in POSITIONS or amplitude not in (-8, 8):
                raise ValueError('Invalid P4 innovation')
            writer.put(POSITIONS.index(int(position)), 4)
            writer.put(int(amplitude > 0), 1)
    writer.aligned()
    payload = writer.get()
    return struct.pack(HEADER, b'L4HY', 9, 3, 8000, n, pre, bright, 320, 320) + struct.pack('<H', len(payload)) + payload


def unpack(blob):
    if len(blob) < 22:
        raise ValueError('Short meta320 header')
    magic, version, mode, rate, n, pre, bright, frame, block = struct.unpack(HEADER, blob[:20])
    if (magic, version, mode, rate, frame, block) != (b'L4HY', 9, 3, 8000, 320, 320):
        raise ValueError('Unsupported meta320 syntax')
    if not 1 <= n <= 64000 or len(blob) != 22+int.from_bytes(blob[20:22], 'little'):
        raise ValueError('Invalid meta320 complete length')
    reader, previous = BitReader(blob[22:]), None
    spectra, parameters, pulses = [], [], []
    for _ in range((n+319)//320):
        vector = compact.get_spectrum(reader, previous, 5)
        spectra.append(vector)
        previous = vector
        parameters.append((reader.get(5), reader.get(7)+18, reader.get(3)*2))
        for _ in range(16):
            pulses.append((POSITIONS[reader.get(4)], 8 if reader.get(1) else -8))
    if reader.o != len(reader.data) or reader.acc:
        raise ValueError('Unexpected meta320 trailing data or padding')
    fields = n, spectra, parameters, pulses, pre, bright
    pack(*fields)
    return fields


def expand(blob):
    n, spectra, params, pulses, pre, bright = unpack(blob)
    return compact.pack(n, 4, spectra, [tuple(value) for value in params for _ in range(2)],
                        pulses, pre, bright)[0]


def decode_model(blob):
    return compact.decode_model(expand(blob))
