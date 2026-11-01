"""Experimental L4HY v6/selector 1, exact scale-only repeat conversion.

This is an explicit protocol adapter, not a header relabel. It copies every
non-parameter source bit and reconstructs all original v5 parameter fields.
The original zero byte padding is regenerated separately for each segment.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
import speech_compact as compact
from lpx4 import BitReader, BitWriter
from output_paths import protect_outputs

VERSION = 6
SELECTOR = 1


def position(reader):
    return reader.o * 8 - reader.n


def copy_span(writer, data, start, end):
    """Copy the actual LSB-first code, preserving even noncanonical choices."""
    for index in range(start, end):
        writer.put((data[index // 8] >> (index % 8)) & 1, 1)


def _header(blob, version):
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise ValueError('Expected a bounded byte stream')
    blob = bytes(blob)
    if not 22 <= len(blob) <= 65535:
        raise ValueError('Stream does not fit the ROM API')
    magic, actual, flags, rate, n, pre, bright, frame, block = struct.unpack(compact.HEADER, blob[:20])
    if (magic, actual, rate, frame, block) != (b'L4HY', version, 8000, 320, 160) or flags & 127 not in (4, 6):
        raise ValueError('Unsupported scale-repeat protocol header')
    if not 1 <= n <= 64000 or pre > 16384 or bright > 11469 or len(blob) != 22 + int.from_bytes(blob[20:22], 'little'):
        raise ValueError('Invalid scale-repeat geometry')
    return blob, n, flags


def _convert(blob, source_version):
    blob, n, flags = _header(blob, source_version)
    forward = source_version == 5
    if forward:
        # Validate positions, all stored/unplayed packets and exact padding.
        compact.unpack(blob)
    body = blob[22:]
    reader = BitReader(body)
    writer = BitWriter()
    if forward:
        writer.put(SELECTOR, 8)
    elif reader.get(8) != SELECTOR:
        raise ValueError('Unsupported scale-repeat selector')
    old_spectrum = None
    previous_scale = None
    params = []
    for _ in range((n + 319) // 320):
        start = position(reader)
        old_spectrum = compact.get_spectrum(reader, old_spectrum, 5 if flags & 127 == 4 else 6)
        copy_span(writer, body, start, position(reader))
        for _ in range(2):
            if forward or previous_scale is None or reader.get(1):
                scale = reader.get(5)
            else:
                scale = previous_scale
            lag = reader.get(7)
            gain = reader.get(3)
            if forward and previous_scale is not None:
                changed = scale != previous_scale
                writer.put(int(changed), 1)
                if changed:
                    writer.put(scale, 5)
            else:
                writer.put(scale, 5)
            writer.put(lag, 7)
            writer.put(gain, 3)
            params.append((scale, lag + 18, gain * 2))
            previous_scale = scale
            for _ in range(4):
                start = position(reader)
                reader.get(10 if flags & 127 == 4 else 17)
                if flags & 128 and reader.get(1):
                    reader.get(10)
                copy_span(writer, body, start, position(reader))
    if reader.o != len(body) or reader.acc or not 0 <= reader.n < 8:
        raise ValueError('Unexpected scale-repeat trailing data or padding')
    writer.aligned()
    payload = writer.get()
    if len(payload) > 65513:
        raise ValueError('Converted stream does not fit the ROM API')
    header = bytearray(blob[:20])
    header[4] = VERSION if forward else 5
    result = bytes(header) + struct.pack('<H', len(payload)) + payload
    if not forward:
        values = compact.unpack(result)
        if values[3] != params:
            raise AssertionError('Scale-repeat parameter reconstruction failed')
    return result


def from_v5(blob):
    """Convert actual validated v5 to the experimental version 6 syntax."""
    return _convert(blob, 5)


def to_v5(blob):
    """Explicitly reconstruct v5 field syntax; do not relabel a v6 header."""
    return _convert(blob, VERSION)


def decode_model(blob):
    """Bound reference adapter: reconstruct the complete v5 stream first."""
    return compact.decode_model(to_v5(blob))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('direction', choices=('from-v5', 'to-v5'))
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    protect_outputs([args.input, Path(__file__)], [args.output])
    result = (from_v5 if args.direction == 'from-v5' else to_v5)(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    print('Converted %d complete bytes' % len(result))


if __name__ == '__main__':
    main()
