"""Independent indexed-bit reader and explicit v6-to-v5 model adapter.

No experimental stream is passed directly to the old v5 model. Reconstruction
uses this reader's own integer bit positions and a separate bit-list writer.
"""
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
import speech_compact


class Reader:
    def __init__(self, data):
        self.data = data
        self.at = 0

    def read(self, width):
        if width < 0 or self.at + width > 8 * len(self.data):
            raise ValueError('Truncated independent bit stream')
        value = 0
        for shift in range(width):
            value |= ((self.data[self.at // 8] >> (self.at % 8)) & 1) << shift
            self.at += 1
        return value


def restore_v5(blob):
    blob = bytes(blob)
    if not 23 <= len(blob) <= 65535:
        raise ValueError('Invalid independent stream length')
    fields = struct.unpack('<4sBBHIHHHH', blob[:20])
    magic, version, flags, rate, samples, pre, bright, frame, block = fields
    profile = flags & 127
    if (magic, version, rate, frame, block) != (b'L4HY', 6, 8000, 320, 160) or profile not in (4, 6):
        raise ValueError('Invalid independent protocol tag')
    if not 1 <= samples <= 64000 or pre > 16384 or bright > 11469 or int.from_bytes(blob[20:22], 'little') != len(blob) - 22:
        raise ValueError('Invalid independent header bounds')
    reader = Reader(blob[22:])
    if reader.read(8) != 1:
        raise ValueError('Unsupported independent selector')
    result = []
    parameters = []
    previous = None
    scale = None
    def append(value, width):
        result.extend((value >> bit) & 1 for bit in range(width))
    def transfer(start):
        for bit in range(start, reader.at):
            result.append((reader.data[bit // 8] >> (bit % 8)) & 1)
    def rice(k, width):
        quotient = 0
        while quotient < 8 and reader.read(1) == 0:
            quotient += 1
        return reader.read(width) if quotient == 8 else (quotient << k) + reader.read(k)
    for _ in range((samples + 319) // 320):
        begin = reader.at
        if reader.read(1):
            delta = reader.read(1)
            if delta and previous is None:
                raise ValueError('Initial delta spectrum')
            width = 5 if profile == 4 else 6
            values = []
            for index in range(10):
                code = rice(width - 4 - delta, width + delta)
                value = previous[index] + (-(code + 1) // 2 if code & 1 else code // 2) if delta else (values[-1] + 1 if values else 0) + code
                if not 0 <= value < (1 << width) or values and value <= values[-1]:
                    raise ValueError('Invalid independent spectrum')
                values.append(value)
            previous = values
        elif previous is None:
            raise ValueError('Initial repeat spectrum')
        transfer(begin)
        for _ in range(2):
            if scale is None or reader.read(1):
                scale = reader.read(5)
            lag = reader.read(7)
            gain = reader.read(3)
            parameters.append((scale, lag + 18, 2 * gain))
            append(scale, 5)
            append(lag, 7)
            append(gain, 3)
            for _ in range(4):
                begin = reader.at
                if profile == 4:
                    reader.read(10)
                else:
                    if reader.read(9) >= 400:
                        raise ValueError('Invalid independent radix20 pulse')
                    reader.read(8)
                if flags & 128 and reader.read(1):
                    if reader.read(6) >= 40:
                        raise ValueError('Invalid independent extra pulse')
                    reader.read(4)
                transfer(begin)
    remaining = 8 * len(reader.data) - reader.at
    if not 0 <= remaining <= 7 or reader.read(remaining):
        raise ValueError('Invalid independent final padding')
    payload = bytearray((len(result) + 7) // 8)
    for bit, value in enumerate(result):
        payload[bit // 8] |= value << (bit % 8)
    header = bytearray(blob[:20])
    header[4] = 5
    restored = bytes(header) + struct.pack('<H', len(payload)) + payload
    return restored, parameters


def decode_model(blob):
    restored, _ = restore_v5(blob)
    return speech_compact.decode_model(restored)
