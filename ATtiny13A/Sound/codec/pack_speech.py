#!/usr/bin/env python3
"""Lossless frame repacker for MicroMusic MiniLPC-8 (six-byte input frames).

Examples:
  python pack_speech.py chego/old.speech.bin chego/new.speech.bin --mode short
  python pack_speech.py vinni/old.speech.bin vinni/new.speech.bin --mode k8zero

The program intentionally refuses frames that the chosen encoding cannot represent.
For K8zero the eighth reflection coefficient must be exactly zero (high nibble 8).
"""
import argparse
from pathlib import Path


def pack(data: bytes, mode: str) -> bytes:
    if len(data) % 6:
        raise ValueError('Input must contain whole six-byte frames')
    output = bytearray()
    for i in range(0, len(data), 6):
        pitch, gain, k12, k34, k56, k78 = data[i:i + 6]
        if not 0 <= gain <= 15:
            raise ValueError(f'Frame {i // 6}: gain out of range')
        if mode == 'short':
            if pitch and not 16 <= pitch <= 30:
                raise ValueError(f'Frame {i // 6}: cannot store pitch {pitch} in four bits')
            code = pitch - 15 if pitch else 0
            first = (code << 4) | gain
            if first == 255:
                raise ValueError(f'Frame {i // 6}: 0xFF conflicts with the end marker')
            output.extend((first, k12, k34, k56, k78))
        elif mode == 'k8zero':
            if k78 >> 4 != 8:
                raise ValueError(f'Frame {i // 6}: eighth coefficient must be exactly zero')
            output.extend((pitch, ((k78 & 15) << 4) | gain, k12, k34, k56))
        else:
            raise ValueError('Unknown mode')
    return bytes(output)


def unpack(data: bytes, mode: str) -> bytes:
    if len(data) % 5:
        raise ValueError('Packed input must consist of five-byte frames')
    output = bytearray()
    for i in range(0, len(data), 5):
        h, a, b, c, d = data[i:i+5]
        if mode == 'short':
            pitch_code, gain = h >> 4, h & 15
            pitch = pitch_code + 15 if pitch_code else 0
            output.extend((pitch, gain, a, b, c, d))
        elif mode == 'k8zero':
            pitch = h
            gain = a & 15
            k7 = a >> 4
            output.extend((pitch, gain, b, c, d, (8 << 4) | k7))
        else:
            raise ValueError('Unknown mode')
    return bytes(output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--mode',required=True,choices=('short','k8zero'))
    a=p.parse_args()
    raw=a.input.read_bytes()
    compressed=pack(raw,a.mode)
    assert unpack(compressed,a.mode)==raw
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(compressed)
    print(f'{a.mode}: {len(raw)} -> {len(compressed)} bytes, exact round trip verified')


if __name__=='__main__': main()
