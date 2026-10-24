"""Lossless PCM-preserving sequential packing of period/residual parameters.

Only fields with zero amplitude are canonicalized; every phase step is retained.
Wave tables stay fixed-width for Flash lookup. This is a file-format prototype,
not proof of a 64-byte-SRAM decoder or its instruction/cycle budget.
"""
import struct
import numpy as np
from colored_period import pack_colored, validate
from period_residual import pack_residual
from period_wave import HOP, SR


class Writer:
    def __init__(self):
        self.output = bytearray()
        self.reservoir = self.bits = 0

    def put(self, value, width):
        if not 0 <= int(value) < 1 << width:
            raise ValueError('Bit-field overflow')
        self.reservoir |= int(value) << self.bits
        self.bits += width
        while self.bits >= 8:
            self.output.append(self.reservoir & 255)
            self.reservoir >>= 8
            self.bits -= 8

    def finish(self):
        return bytes(self.output)+(bytes([self.reservoir]) if self.bits else b'')


class Reader:
    def __init__(self, payload):
        self.payload, self.position = payload, 0

    def get(self, width):
        if self.position+width > len(self.payload)*8:
            raise ValueError('Truncated compact fields')
        value = 0
        for i in range(width):
            value |= ((self.payload[self.position//8] >> (self.position % 8)) & 1) << i
            self.position += 1
        return value

    def finish(self):
        if len(self.payload) != (self.position+7)//8:
            raise ValueError('Unexpected compact data')
        if self.position % 8 and self.payload[-1] >> (self.position % 8):
            raise ValueError('Nonzero compact padding')


def repeat_write(writer, value, previous, width):
    writer.put(int(value != previous), 1)
    if value != previous:
        writer.put(value, width)
    return value


def repeat_read(reader, previous, width):
    return reader.get(width) if reader.get(1) else previous


def pack_compact(model):
    colored = model['schema'] == 'period-colored-v1'
    (pack_colored if colored else pack_residual)(model)
    base = model['base']
    header = struct.pack('<4sBHHHH', b'PX\x01\x00', int(colored), base['samples'],
                         base['initial_phase_u16'], base['scale_u16'], model['scale_u16'])
    book = np.asarray(base['codebook'], dtype=int).ravel() & 15
    payload = bytearray(header)
    payload.extend((book[::2] | book[1::2] << 4).astype(np.uint8).tobytes())
    if colored:
        noise = np.asarray(model['noise_filters'], dtype=int).ravel() & 15
        payload.extend((noise[::2] | noise[1::2] << 4).astype(np.uint8).tobytes())
    writer = Writer()
    previous_pitch = previous_gain = previous_index = previous_level = previous_color = 0
    for frame, code in zip(base['frames'], model['gains']):
        pitch, index, gain, voiced = frame
        delta = pitch-previous_pitch
        if delta == 0:
            writer.put(0, 1)
        else:
            writer.put(1, 1)
            if abs(delta) == 1:
                writer.put(0, 1)
                writer.put(int(delta < 0), 1)
            else:
                writer.put(1, 1)
                if 2 <= abs(delta) <= 5:
                    writer.put(0, 1)
                    writer.put(2*(abs(delta)-2)+int(delta < 0), 3)
                else:
                    writer.put(1, 1)
                    writer.put(pitch, 8)
        previous_pitch = pitch
        previous_gain = repeat_write(writer, gain, previous_gain, 3)
        if gain:
            writer.put(voiced, 1)
            previous_index = repeat_write(writer, index, previous_index, 4)
        level, color = code & 15, code >> 4
        previous_level = repeat_write(writer, level, previous_level, 4)
        if colored and level:
            previous_color = repeat_write(writer, color, previous_color, 2)
    payload.extend(writer.finish())
    return bytes(payload)


def unpack_compact(payload):
    if len(payload) < 269:
        raise ValueError('Truncated compact header')
    magic, colored, samples, initial, scale, residual_scale = struct.unpack('<4sBHHHH', payload[:13])
    if magic != b'PX\x01\x00' or colored not in (0, 1) or not samples:
        raise ValueError('Invalid compact header')
    fixed = 269+12*colored
    if len(payload) < fixed:
        raise ValueError('Truncated compact tables')
    def nibbles(data):
        values = np.frombuffer(data, dtype=np.uint8).astype(int)
        values = np.column_stack((values & 15, values >> 4)).ravel()
        values[values >= 8] -= 16
        return values
    book = nibbles(payload[13:269]).reshape(16, 32).tolist()
    reader = Reader(payload[fixed:])
    frames, codes = [], []
    pitch = gain = index = level = color = 0
    for _ in range((samples+HOP-1)//HOP):
        if reader.get(1):
            if not reader.get(1):
                pitch += -1 if reader.get(1) else 1
            elif not reader.get(1):
                code = reader.get(3)
                pitch += (code//2+2)*(-1 if code & 1 else 1)
            else:
                pitch = reader.get(8)
        if not 0 <= pitch <= 255:
            raise ValueError('Invalid compact pitch delta')
        gain = repeat_read(reader, gain, 3)
        if gain:
            voiced = reader.get(1)
            index = repeat_read(reader, index, 4)
            frames.append([pitch, index, gain, voiced])
        else:
            frames.append([pitch, 0, 0, 0])
        level = repeat_read(reader, level, 4)
        if colored and level:
            color = repeat_read(reader, color, 2)
        codes.append(level | (color << 4 if level and colored else 0))
    reader.finish()
    base = dict(schema='period-wave-v2', sample_rate=SR, samples=samples, hop=HOP,
                initial_phase_u16=initial, scale_u16=scale, codebook=book, frames=frames)
    model = dict(schema='period-colored-v1' if colored else 'period-residual-v1', base=base,
                 scale_u16=residual_scale, gains=codes)
    if colored:
        model['noise_filters'] = nibbles(payload[269:281]).reshape(3, 8).tolist()
    (pack_colored if colored else pack_residual)(model)
    return model
